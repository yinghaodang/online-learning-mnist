# 在线机器学习

## 前言
继承自 `https://github.com/yinghaodang/online-learning`
主要是更改了一下模型，优化了一些细节

流程依旧是
1. 从kafka取数据
2. 使用flink处理流数据，进行模型训练
3. 模型保存在Redis里
4. 新增一个gradio写的应用程序，展示效果

数据集采用MNIST，使用CPU推理(暂不支持批处理)

在我看来，在线机器学习相较于传统的离线机器学习没有特别的优势，劣势反倒是一大堆。开发过程复杂难调试，训练速度缓慢难拓展（中间模型要使用redis频繁中转），缺少框架支撑。
在线机器学习唯一的优势就是抱紧了`flink`的大腿，在处理实时数据方面确实是优秀的。无奈可用场景太少！

比方说，我要在线训练一个图片分类模型，完全可以将一定量的数据存在本地，训练一个通用的模型应对很长一段时间的数据流。
实时需要训练模型的场景非常稀有，需要实时训练，说明数据来源的分布是变化的，10分钟前的数据规律和10分钟后的数据规律不一样（类似前10分钟，指鹿为鹿，后10分钟，指鹿为马，要扭转原有模型）

实时在线推理倒是让我眼前一亮，抱住flink的大腿，使用`kafka + flink`的体系提供的服务，吞吐量应该是普通服务的好几倍吧。

后续，需要研究 矢量化的UDF函数，要求支持数据批处理

----------
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
只能加一点骚操作，类似于下面：
```
ln -s /home/aiuser/yhd-workspace/projects/online-machine-learning-mnist/utils /home/aiuser/miniconda3/envs/online-learning/lib/python3.8/site-packages/utils
```
将`utils`模块添加到能被`flink`检测到的地方

其余依赖安装

```
pip insatll -r requirements.txt && \
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

如果是本地安装模型
```
flink run -m localhost:8081 -py stream.py -pyexec $(which python)
```

如果是docker部署，
    
正在研究

### 运行demo应用

这个应用是用`gradio`写的，而`flink-1.14`又比较老了，两者在`numpy`版本上起了冲突，就多开一个虚拟环境吧，这点属实是没有计划到。需要本地安装的话，依赖包可以看`Dockerfile-gradio`文件。
```
python model_server.py
```

也可以使用docker部署, 

```
docker build -t online-learning-gradio -f Dockerfile-gradio .
```

我构建了一份镜像，可以使用`docker pull reg.hdec.com/pdc/online-learning-gradio:v1`下载

启动容器使用：进入到`README.md`所在目录
```
docker run -d -p 7860:7860 -v $(pwd)/model_server.py:/root/online-learning-demo/model_server.py online-learning-gradio
```
这样访问7860端口即可

### 注意事项

1. `stream.py` 要和 `flink-xxx-connector-kafka-xxx.jar` 文件放在同一个目录下

2. `Dockerfile-gradio`是应用程序的`Dockerfile`, 使用的时候将`model_server.py`挂载进去，不然默认的redis数据库以及模型名称可以对应不上。
这个应用的主要作用是看不同训练时间的模型的效果。