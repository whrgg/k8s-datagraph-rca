import sys
import time
import logging
import pexpect
import subprocess
from pathlib import Path


logger = logging.getLogger(__name__)

# 本地镜像仓库配置，与 kind 官方文档保持一致
LOCAL_REGISTRY_NAME = "kind-registry"
LOCAL_REGISTRY_PORT = 5001


def run_command_with_wait(command, timeout=600, encoding='utf-8', stream_output=False, wait_for_string=None):
    """
    Run a command and wait for it to complete or for a specific string to appear.
    
    参数：
        command: 要执行的命令
        timeout: Maximum time to wait for command completion (in seconds)
        encoding: Character encoding for output
        stream_output: If True, stream the subprocess output to stdout
        wait_for_string: Optional string pattern to wait for before considering command complete
        
    返回：
        tuple: (exit_code, output)
    """
    logger.info("执行命令：%s", command)

    child = pexpect.spawn(command, encoding=encoding, timeout=timeout)
    if stream_output:
        child.logfile_read = sys.stdout
    
    try:
        if wait_for_string:
            # 等待指定字符串出现
            logger.info("等待输出模式：%s", wait_for_string)
            child.expect(wait_for_string)
            output = child.before
            logger.info("已匹配预期输出：%s", wait_for_string)
            # 继续等待 EOF，确保进程真正结束
            try:
                child.expect(pexpect.EOF, timeout=10)
            except pexpect.TIMEOUT:
                logger.debug("Process still running after string appeared, closing...")
        else:
            # 等待进程结束
            child.expect(pexpect.EOF)
            output = child.before
        
        child.close()
        if output:
            logger.debug("Command output for '%s':\n%s", command, output.strip())
        return child.exitstatus, output
    except pexpect.TIMEOUT:
        logger.error("命令超时（%s 秒）：%s", timeout, command)
        child.close(force=True)
        return -1, None
    except Exception as e:
        logger.exception("执行命令失败 '%s'：%s", command, e)
        child.close(force=True)
        return -1, None


def configure_kind_registry(
    cluster_name="kind",
    registry_port: int = LOCAL_REGISTRY_PORT,
) -> bool:
    """
    Configure the kind cluster to use the local registry.
    
    Based on official kind documentation:
    https://kind.sigs.k8s.io/docs/user/local-registry/
    
    This:
    1. Creates the registry config directory on each node
    2. Configures containerd to use the local registry
    3. Connects the registry to the kind network
    4. Adds a ConfigMap for registry discovery
    
    参数：
        cluster_name: Name of the kind cluster (default: "kind")
        registry_port: Port the registry is running on (default: 5001)
        
    返回：
        bool: True if configuration successful, False otherwise
    """
    logger.info("配置 kind 集群 '%s' 使用本地 Registry", cluster_name)
    
    registry_dir = f"/etc/containerd/certs.d/localhost:{registry_port}"
    
    # 第 0 步：将 registry 连接到 kind 网络
    logger.info("Connecting registry to kind network")
    try:
        # 如果 registry 容器存在，则将其连接到 kind 网络
        cmd = f"docker network connect {cluster_name} {LOCAL_REGISTRY_NAME} 2>/dev/null || true"
        subprocess.run(cmd, shell=True, capture_output=True)
        logger.info("Registry connected to kind network")
    except Exception as e:
        logger.warning("Could not connect registry to kind network: %s", e)
    
    # 第 1 步：为所有节点添加 registry 配置
    logger.info("Configuring containerd on cluster nodes")
    try:
        # 获取节点列表
        get_nodes_cmd = f"kind get nodes --name {cluster_name}"
        result = subprocess.run(get_nodes_cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error("获取集群节点失败：%s", result.stderr)
            return False
        
        nodes = [n for n in result.stdout.strip().split('\n') if n]
        
        for worker in nodes:
            logger.info("Configuring registry on worker node: %s", worker)
            
            # 1. 配置 localhost:5001（适用于 localhost:5001/image 这类显式引用）
            cmd = f"docker exec {worker} mkdir -p /etc/containerd/certs.d/localhost:{registry_port}"
            subprocess.run(cmd, shell=True, check=True)
            
            # 使用 registry 容器主机名，Docker DNS 会自动解析
            hosts_config = (
                f"[host.\\\"http://{LOCAL_REGISTRY_NAME}:5000\\\"]\n"
            )
            
            cmd = (
                f"docker exec {worker} "
                f"bash -c \"cat > /etc/containerd/certs.d/localhost:{registry_port}/hosts.toml << 'EOF'\n"
                f"{hosts_config}"
                f"EOF\""
            )
            subprocess.run(cmd, shell=True, check=True)

            # 2. 配置 docker.io 镜像源（用于透明缓存标准镜像）
            cmd = f"docker exec {worker} mkdir -p /etc/containerd/certs.d/docker.io"
            subprocess.run(cmd, shell=True, check=True)

            mirror_config = (
                f"server = \\\"https://registry-1.docker.io\\\"\n"
                f"\n"
                f"[host.\\\"http://{LOCAL_REGISTRY_NAME}:5000\\\"]\n"
                f"  capabilities = [\\\"pull\\\", \\\"resolve\\\"]\n"
            )

            cmd = (
                f"docker exec {worker} "
                f"bash -c \"cat > /etc/containerd/certs.d/docker.io/hosts.toml << 'EOF'\n"
                f"{mirror_config}"
                f"EOF\""
            )
            subprocess.run(cmd, shell=True, check=True)
            
            logger.info("Worker node %s configured with registry mirror", worker)
        
    except subprocess.CalledProcessError as e:
        logger.warning("Issue configuring worker nodes: %s", e)
    
    # 第 2 步：登记本地镜像仓库信息
    logger.info("Documenting local registry in ConfigMap")
    try:
        config_map_yaml = (
            "apiVersion: v1\n"
            "kind: ConfigMap\n"
            "metadata:\n"
            "  name: local-registry-hosting\n"
            "  namespace: kube-public\n"
            "data:\n"
            "  localRegistryHosting.v1: |\n"
            f"    host: \"localhost:{registry_port}\"\n"
            "    help: \"https://kind.sigs.k8s.io/docs/user/local-registry/\"\n"
        )
        
        cmd = f"echo '{config_map_yaml}' | kubectl apply -f -"
        subprocess.run(cmd, shell=True, check=True, capture_output=True)
        logger.info("Local registry documented in kube-public/local-registry-hosting ConfigMap")
    except subprocess.CalledProcessError as e:
        logger.warning("创建本地 Registry ConfigMap 失败：%s", e)

    logger.info("Registry configuration complete - local registry enabled with fallback to default registries")
    return True


def setup_cluster_and_aiopslab(
    problem_id,
    kind_config_path=None,
    aiopslab_dir=None,
    cluster_timeout=600,
    setup_timeout=900,
    stream_cluster_output=False,
    stream_cli_output=False,
    enable_local_registry=True,
):
    """
    Set up the experiment environment: create kind cluster and initialize AIOpsLab.
    
    参数：
        problem_id: 要启动的问题/实验 ID
        kind_config_path: Path to kind config file (optional, uses default if not provided)
        aiopslab_dir: Directory where AIOpsLab is located (where cli.py and pyproject.toml are)
                      If None, uses the directory of this script
        cluster_timeout: Timeout for cluster creation in seconds
        setup_timeout: Timeout for problem setup in seconds
        stream_cluster_output: If True, stream kind cluster command output to stdout
        stream_cli_output: If True, stream AIOpsLab CLI output to stdout
        enable_local_registry: If True, configure the cluster to use the local registry
        
    返回：
        bool: True if setup successful, False otherwise
    """
    script_dir = Path(__file__).parent
    
    # 确定 AIOpsLab 目录
    if aiopslab_dir is None:
        aiopslab_dir = script_dir
    else:
        aiopslab_dir = Path(aiopslab_dir).resolve()
    
    logger.info("AIOpsLab directory: %s", aiopslab_dir)
    
    # 第 1 步：创建 kind 集群
    logger.info("=== 步骤 1：创建 Kind 集群 ===")
    
    if kind_config_path is None:
        kind_config_path = aiopslab_dir / "kind" / "kind-config-x86.yaml"
    else:
        kind_config_path = Path(kind_config_path)
    
    if not kind_config_path.exists():
        logger.error("Kind config file not found at %s", kind_config_path)
        return False
    
    cluster_command = f"kind create cluster --config {kind_config_path}"
    exit_code, _ = run_command_with_wait(
        cluster_command,
        timeout=cluster_timeout,
        stream_output=stream_cluster_output,
    )
    
    if exit_code != 0:
        logger.error("创建 Kind 集群失败（退出码：%s）", exit_code)
        return False
    
    logger.info("Kind 集群创建成功")
    
    # 给集群一些时间完成稳定
    logger.info("等待 30 秒以便集群稳定...")
    time.sleep(30)
    
    # 第 2 步：可选，为集群配置 registry
    if enable_local_registry:
        logger.info("=== STEP 2: Configure local registry ===")
        if not configure_kind_registry("kind", LOCAL_REGISTRY_PORT):
            logger.warning("Registry 配置失败，将继续运行（不使用本地 Registry）")
    
    # 第 3 步：在后台启动 AIOpsLab CLI
    logger.info("=== STEP 3: Start AIOpsLab CLI ===")

    # 切换到 AIOpsLab 目录，并从该目录运行 poetry
    command = f"cd {aiopslab_dir} && poetry run python cli.py"
    logger.info("启动 CLI 命令：%s", command)
    
    # 使用带登录态的 bash (-l)，以便在 tmux 中正确加载环境
    # 这样可以确保 PATH、环境变量和 shell 初始化都生效
    full_command = f"bash -l -c '{command}'"
    logger.info("启动 CLI（环境已注入）：%s", full_command)
    
    child = pexpect.spawn('/bin/bash', ['-l', '-c', command], encoding='utf-8', timeout=setup_timeout)
    if stream_cli_output:
        child.logfile_read = sys.stdout
    
    try:
        # 等待第一个提示符出现
        logger.info("等待 CLI 启动...")
        child.expect('aiopslab>', timeout=30)
        logger.info("CLI 已启动")
        if child.before:
            logger.debug("CLI initial output:\n%s", child.before.strip())
        
        # 发送 start 命令
        start_cmd = f"start {problem_id}"
        logger.info("Sending CLI command: %s", start_cmd)
        child.sendline(start_cmd)
        
        logger.info(
            "等待故障场景初始化（超时：%s 秒）...",
            setup_timeout,
        )
        logger.debug(
            "Initialization includes loading the problem, displaying context, and the first env message",
        )
        
        child.expect('aiopslab>', timeout=setup_timeout)
        logger.info("上下文已展示")
        if child.before:
            logger.debug("CLI output before context prompt:\n%s", child.before.strip())
        
        child.expect('aiopslab>', timeout=setup_timeout)
        logger.info("故障场景已完全初始化，可开始实验")
        if child.before:
            logger.debug("CLI output before ready prompt:\n%s", child.before.strip())
        
        logger.info("环境已就绪")
        logger.info("场景 '%s' 已初始化", problem_id)
        logger.info("CLI 已在后台运行，可开始实验。")
        logger.info("实验结束后请调用 cleanup_cluster()。")
        
        return True
        
    except Exception as e:
        logger.exception("初始化 AIOpsLab 失败：%s", e)
        try:
            child.close(force=True)
        except:
            pass
        return False


def cleanup_cluster(cluster_timeout=120, stream_output=False):
    """
    Delete the kind cluster and wait for confirmation of node deletion.
    
    参数：
        cluster_timeout: Timeout for cluster deletion in seconds
        stream_output: If True, stream the deletion command output to stdout
        
    返回：
        bool: True if successful, False otherwise
    """
    logger.info("正在删除 Kind 集群")
    
    delete_command = "kind delete cluster"
    # 等待出现 "Deleted nodes:"，以确认节点已删除
    delete_exit_code, output = run_command_with_wait(
        delete_command,
        timeout=cluster_timeout,
        stream_output=stream_output,
        wait_for_string=r"Deleted nodes:\s*\[.*\]",
    )
    
    if delete_exit_code != 0:
        logger.warning(
            "删除 Kind 集群失败（退出码：%s）",
            delete_exit_code,
        )
        return False
    else:
        logger.info("Kind 集群已删除")
        if output:
            logger.debug("Cluster deletion output:\n%s", output)
        return True
