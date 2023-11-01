import os
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.table import StreamTableEnvironment, EnvironmentSettings, DataTypes
from pyflink.table.udf import ScalarFunction, udf
from onml.models.mnist_cnn import Net


# kafka地址, 消费者id
kafka_servers = "10.215.58.30:9092"
kafka_consumer_group_id = "group0"

# kafka topic
source_topic = "mnist"
sink_topic = "mnist_predict"

# redis 参数
# 由于redis在UDF函数内部调用，其参数需在UDF内指定

# pyflink 流处理环境
env = StreamExecutionEnvironment.get_execution_environment()
env_settings = EnvironmentSettings.new_instance().in_streaming_mode().use_blink_planner().build()
t_env = StreamTableEnvironment.create(env, environment_settings=env_settings)
t_env.get_config().get_configuration().set_boolean("python.fn-execution.memory.managed", True)


# 指定jar包依赖
dir_kafka_sql_connect = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                                     'flink-sql-connector-kafka_2.11-1.14.4.jar')
t_env.get_config().get_configuration().set_string("pipeline.jars", 'file://' + dir_kafka_sql_connect)


class Model(ScalarFunction):

    def __init__(self):
        from datetime import datetime
        import torch.optim as optim
        from torch.optim.lr_scheduler import StepLR
        from onml.models.mnist_cnn import Net

        # Redis参数
        self.current_time = str(datetime.now().strftime("%Y-%m-%d %H"))
        self.model_name = 'mnist-{}'.format(self.current_time)
        self.redis_params = dict(host='localhost', password='redis_password', port=6379, db=0)
        self.clf = Net()
        self.load_model(self.current_time)

        # 机器学习超参数
        self.device = "cpu"
        self.lr = 1.0    # 学习率
        self.gamma = 0.7    # 优化器参数
        self.optimizer = optim.Adadelta(Net().parameters(), lr=self.lr)
        self.scheduler = StepLR(self.optimizer, step_size=1, gamma=self.gamma)

        # 保存模型
        self.interval_dump_seconds = 360       # 模型保存间隔时间为 6 分钟
        self.last_dump_time = datetime.now()   # 上一次模型保存时间

        # 自定义指标
        self.metric_counter = None  # 从作业开始至今的所有样本数量
        self.metric_predict_acc = 0  # 模型预测的准确率（用过去 10 条样本来评估）
        self.metric_distribution_y = None  # 标签 y 的分布
        self.metric_total_10_sec = None  # 过去 10 秒内训练过的样本数量
        self.metric_right_10_sec = None  # 过去 10 秒内的预测正确的样本数
        print("__init__方法被调用")

    def open(self, function_context):
        # 访问指标系统，并注册指标
        # 定义 Metric Group 名称为 online_ml 以便于在 webui 查找
        # Metric Group + Metric Name 是 Metric 的唯一标识
        metric_group = function_context.get_metric_group().add_group("online_ml")

        self.metric_counter = metric_group.counter('sample_count')  # 训练过的样本数量
        metric_group.gauge("prediction_acc", lambda: int(self.metric_predict_acc * 100))

        # 统计过去 10 秒内的样本量、预测正确的样本量
        self.metric_total_10_sec = metric_group.meter("total_10_sec", time_span_in_seconds=10)
        self.metric_right_10_sec = metric_group.meter("right_10_sec", time_span_in_seconds=10)
        print("open方法被调用")

    def eval(self, x, y):
        import torch
        import torch.nn.functional as F
        from datetime import datetime
        from onml.preprocess import preprocess
        
        # data 为 1 * 1 * 28 * 28 格式
        data = preprocess(x)
        target = torch.tensor([y])
        data, target = data.to(self.device), target.to(self.device)
        self.optimizer.zero_grad()
        output = self.clf(data)
        # 此次推理结果
        pred = output.argmax(dim=1, keepdim=True)
        loss = F.nll_loss(output, target)
        loss.backward()
        self.dump_model()

        # 更新指标
        self.metric_counter.inc(1)    # 训练过的样本数量 + 1
        self.metric_total_10_sec.mark_event(1)    # 10s 内处理的数量
        if pred[0][0] == y:
            self.metric_right_10_sec.mark_event(1)    # 10s 内推理正确的数量
        self.metric_predict_acc = self.metric_right_10_sec.get_count() / self.metric_total_10_sec.get_count()  # 准确率

        if (datetime.now() - self.last_dump_time).seconds >= self.interval_dump_seconds:
            print("loss is {}".format(loss))
        return pred[0][0]
    
    def load_model(self, key):
        import io
        import redis
        import torch
        from onml.models.mnist_cnn import Net

        key = "online_ml_model"
        r = redis.StrictRedis(**self.redis_params)
        model_dict = r.get(key)
        buffer = io.BytesIO(model_dict)
        buffer.seek(0)
        self.clf = torch.load(buffer)

    def dump_model(self):
        from datetime import datetime
        import redis
        import torch
        import io

        # 保存模型
        if (datetime.now() - self.last_dump_time).seconds >= self.interval_dump_seconds:
            r = redis.StrictRedis(**self.redis_params)
            buffer = io.BytesIO()
            torch.save(self.clf, buffer)
            buffer.seek(0)
            model_bytes = buffer.read()

            self.current_time = str(datetime.now().strftime("%Y-%m-%d %H"))
            self.model_name = 'mnist-{}'.format(self.current_time)    # 更新模型名称

            r.set(self.model_name, model_bytes)

            self.last_dump_time = datetime.now()    # 更新保存时间


model = udf(Model(), input_types=[DataTypes.ARRAY(DataTypes.INT()), DataTypes.TINYINT()],
            result_type=DataTypes.TINYINT())
t_env.register_function('train_and_predict', model)

# ====== 创建源表(source) ======
# 使用 Kafka-SQL 连接器从 Kafka 实时消费数据。

t_env.execute_sql(f"""
CREATE TABLE source (
    x ARRAY<INT>,            -- 图片数据
    actual_y TINYINT,            -- 实际数字
    ts TIMESTAMP(3)              -- 图片产生时间
) with (
    'connector' = 'kafka',
    'topic' = '{source_topic}',
    'properties.bootstrap.servers' = '{kafka_servers}',
    'properties.group.id' = '{kafka_consumer_group_id}',
    'scan.startup.mode' = 'latest-offset',
    'json.fail-on-missing-field' = 'false',
    'json.ignore-parse-errors' = 'true',
    'format' = 'json'
)
""")

# ====== 创建结果表(sink) ======
# 将统计结果实时写入到 Kafka

t_env.execute_sql(f"""
CREATE TABLE sink (
    x ARRAY<INT>,              -- 图片数据
    actual_y TINYINT,              -- 实际数字
    predict_y TINYINT              -- 预测数字
) with (
    'connector' = 'kafka',
    'topic' = '{sink_topic}',
    'properties.bootstrap.servers' = '{kafka_servers}',
    'properties.group.id' = '{kafka_consumer_group_id}',
    'scan.startup.mode' = 'latest-offset',
    'json.fail-on-missing-field' = 'false',
    'json.ignore-parse-errors' = 'true',
    'format' = 'json'
)
""")


# ====== 流处理任务 ======
# 在线学习
t_env.sql_query("""
SELECT
    x,
    actual_y,
    train_and_predict(x, actual_y) AS predict_y
FROM
    source
""").insert_into("sink")

t_env.execute('Classifier Model Train')
