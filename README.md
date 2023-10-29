# 在线机器学习

继承自 `https://github.com/yinghaodang/online-learning`
主要是更改了一下模型，优化了一些细节

流程依旧是 1. 从kafka取数据
          2. 使用flink处理流数据，进行模型训练
          3. 模型保存在Redis里
          4. 新增一个gradio写的应用程序，展示效果

数据集采用MNIST，使用CPU推理(暂不支持批处理)

## 部署流程

### docker-compose

使用`docker-compose.yml`部署`Redis`, `Kafka`, 自行修改相关参数

### 本地部署flink 1.14

参见文档`https://nightlies.apache.org/flink/flink-docs-release-1.14/zh/`

启动本地集群，检查`flink`版本，要求必须是1.14版本

### 数据传输

`python kafka_producer.py`

### 提交任务

本次新增了一个`utils`的文件夹，在测试过程中，一直报错，说无法找到该模块，这应该和`flink`调用python程序有关。
只能加一点骚操作，
`ln -s /home/aiuser/yhd-workspace/projects/online-machine-learning-mnist/utils /home/aiuser/miniconda3/envs/online-learning/lib/python3.8/site-packages/utils`
将`utils`模块添加到能被`flink`检测到的地方


1.

### 运行demo应用

这个应用是用`gradio`写的，而`flink-1.14`又比较老了，两者在`numpy`版本上起了冲突，就多开一个虚拟环境吧，这点属实是没有计划到。
`python model_server.py`


### 注意事项

`stream.py` 要和 `flink-xxx-connector-kafka-xxx.jar` 文件放在同一个目录下

