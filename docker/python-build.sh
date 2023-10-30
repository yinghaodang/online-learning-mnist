###########################################
#  此程序用于初始化一些conda配置
#  此程序适用于写入Dockerfile
#  不支持除了bash外的其他shell，不支持非root用户
###########################################

# Miniconda安装包，可自行调整
MinicondaScript="https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py38_23.5.0-3-Linux-x86_64.sh"
# MinicondaScript="https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py310_23.5.1-0-Linux-x86_64.sh"
# 获取当前脚本所在的目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 检查脚本同级目录下是否有miniconda.sh文件
if [ -e "$SCRIPT_DIR/miniconda.sh" ]; then
    echo "miniconda.sh found. Running..."
    bash "$SCRIPT_DIR/miniconda.sh" -b -p $HOME/miniconda
else
    echo "miniconda.sh not found."
    wget -O "$SCRIPT_DIR/miniconda.sh" ${MinicondaScript}
    bash "$SCRIPT_DIR/miniconda.sh" -b -p $HOME/miniconda
fi

# conda换成清华源
cat <<EOF > $HOME/.condarc
channels:
  - defaults
show_channel_urls: true
default_channels:
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r
  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/msys2
custom_channels:
  conda-forge: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
  msys2: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
  bioconda: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
  menpo: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
  pytorch: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
  pytorch-lts: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
  simpleitk: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
  deepmodeling: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/
EOF

# 清除conda缓存
$HOME/miniconda/bin/conda clean -i -y

# 修改pip源(全局)
$HOME/miniconda/bin/pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 升级pip
$HOME/miniconda/bin/python -m pip install --upgrade pip

# 初始化bash，默认进入base环境
cat <<'EOF' >> $HOME/.bashrc
__conda_setup="$('/root/miniconda/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    echo "出现错误，正在退出程序"
fi
unset __conda_setup

export LANG=C.UTF-8
EOF

# 设置python pip conda 软链接
ln -s /root/miniconda/bin/python /usr/bin/python
ln -s /root/miniconda/bin/pip /usr/bin/pip
ln -s /root/miniconda/condabin/conda /usr/bin/conda