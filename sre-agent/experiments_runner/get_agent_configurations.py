import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def load_agent_configurations(agents_dir=None, only_executable=True):
    """
    Load agent configuration JSON files from a directory.

    参数：
        agents_dir (str | Path | None): Directory containing configuration files.
            Defaults to "<this_module>/agent-configurations".
        only_executable (bool): When True, include only configurations whose
            "execute" flag is truthy. When False, include all configurations.

    返回：
        list[dict]: Parsed configuration dictionaries annotated with `_source_file`.
            目录不存在或无有效配置时返回空列表。
    """
    
    if agents_dir is None:
        agents_dir = Path(__file__).parent / "agent-configurations"
    else:
        agents_dir = Path(agents_dir)
    
    logger.info("从以下路径加载 Agent 配置：%s", agents_dir.absolute())
    
    if not agents_dir.exists():
        logger.error("目录不存在：%s", agents_dir)
        return []
    
    agent_configurations = []
    json_files = sorted(agents_dir.glob("*.json"))
    
    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                agent_config = json.load(f)
                agent_config['_source_file'] = json_file.name
                if agent_config.get("execute", False) and only_executable:
                    agent_configurations.append(agent_config)
                else:
                    logger.warning(
                        "agent_config %s skipped as user specified",
                        agent_config.get("name", "unknown"))
                logger.info("已加载 Agent 配置：%s", json_file.name)
        except json.JSONDecodeError as e:
            logger.error("加载 %s 失败：%s", json_file.name, e)
        except Exception as e:
            logger.exception("Unexpected error with %s: %s", json_file.name, e)
    
    logger.info("共加载 Agent 配置数：%s", len(agent_configurations))
    return agent_configurations