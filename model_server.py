import torch
import torch.nn.functional as F
from torchvision import datasets, transforms
import redis
import pickle
import gradio as gr
from PIL import Image

from utils.models.mnist_cnn import Net

# ======加载数据集 & 加载模型========
def load_model():
    redis_params = dict(host='localhost', password='redis_password', port=6379, db=0)
    model_name = "online_ml_model"
    r = redis.StrictRedis(**redis_params)
    clf = pickle.loads(r.get(model_name))

    return clf

model = load_model()


# =======推理函数=======
def mnist_infer(data):
    # 进入推理模式
    model.eval()
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])

    # 将图片转化成黑白格式,并拓展一个维度
    data = Image.fromarray(data.astype('uint8'), 'RGB')
    data = data.convert('L')
    data = transform(data).unsqueeze(1)

    # 模型推理
    output = model(data)

    pred = output.argmax(dim=1, keepdim=True)    # 推理结果
    probabilities = F.softmax(output, dim=1)     # 各结果的可能性
    probabilities = {i: value for i, value in enumerate(probabilities[0].tolist())}
    print("probabilities is {}".format(probabilities))
    print("pred is {}".format(pred))
    return probabilities


inputs = gr.inputs.Image()
outputs = gr.outputs.Label(num_top_classes=3)
gr.Interface(fn=mnist_infer, inputs=inputs, outputs=outputs).launch()