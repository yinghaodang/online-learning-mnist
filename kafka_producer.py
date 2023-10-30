import numpy as np
from json import dumps
from time import sleep
from datetime import datetime
from kafka import KafkaProducer
from torchvision import datasets, transforms

# ======== 设置 =========
max_msg_per_second = 10  # 每秒钟的最大图片数，数据集共有 60000 张 , 可以传输 100 分钟
topic = "mnist"  # kafka topic
bootstrap_servers = ['localhost:9092']


def convert(image):
    return np.array(image).flatten().tolist()


dataset = datasets.MNIST('mnist_data')
transform = transforms.Compose([convert])


def write_data():
    producer = KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda x: dumps(x).encode('utf-8')
    )
    print("开始传输")
    while True:
        for image, target in dataset:
            cur_data = {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "x": transform(image),
                "actual_y": target
            }
            producer.send(topic, value=cur_data)

            sleep(1 / max_msg_per_second)
        print("传输完成一次")


write_data()
