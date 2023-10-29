import os
from datetime import datetime
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.table import StreamTableEnvironment, EnvironmentSettings, DataTypes
from pyflink.table.udf import ScalarFunction, udf

import torch
import torch.nn.functional as F
import torch.optim as optim
from torch.optim.lr_scheduler import StepLR

import sys
utils_module_path = os.path.abspath(os.path.dirname(__file__))
sys.path.append(utils_module_path)

from utils.models.mnist_cnn import Net
from utils.preprocess import preprocess

import redis
import pickle
import logging

# kafka地址, 消费者id
kafka_servers = "10.215.58.30:9092"
kafka_consumer_group_id = "group0"

# kafka topic
source_topic = "mnist"
sink_topic = "mnist_predict"

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
        # Redis参数
        self.model_name = 'online_ml_model'
        self.redis_params = dict(host='localhost', password='redis_password', port=6379, db=0)
        self.clf = self.load_model()

        # 训练基本参数
        self.device = "cpu"
        self.lr = 1.0    # 学习率
        self.gamma = 0.7    # 优化器参数
        self.optimizer = optim.Adadelta(self.clf.parameters(), lr=self.lr)
        self.scheduler = StepLR(self.optimizer, step_size=1, gamma=self.gamma)

        # 保存模型
        self.interval_dump_seconds = 300       # 模型保存间隔时间为 5 分钟
        self.last_dump_time = datetime.now()   # 上一次模型保存时间

    def eval(self, x, y):
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
        return pred[0][0]

    def load_model(self):
        """
        加载模型，如果 redis 里存在模型，则优先从 redis 加载，否则初始化一个新模型
        :return:
        """
        r = redis.StrictRedis(**self.redis_params)
        clf = None
        try:
            clf = pickle.loads(r.get(self.model_name))
        except TypeError:
            logging.info('Redis 内没有指定名称的模型，因此初始化一个新模型')
        except (redis.exceptions.RedisError, TypeError, Exception):
            logging.warning('Redis 出现异常，因此初始化一个新模型')
        finally:
            clf = clf or Net()

        return clf

    def dump_model(self):
        """
        当距离上次尝试保存模型的时刻过了指定的时间间隔，则保存模型
        :return:
        """
        if (datetime.now() - self.last_dump_time).seconds >= self.interval_dump_seconds:
            r = redis.StrictRedis(**self.redis_params)

            try:
                r.set(self.model_name, pickle.dumps(self.clf, protocol=pickle.HIGHEST_PROTOCOL))
            except (redis.exceptions.RedisError, TypeError, Exception):
                logging.warning('无法连接 Redis 以存储模型数据')

            self.last_dump_time = datetime.now()  # 无论是否更新成功，都更新保存时间


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