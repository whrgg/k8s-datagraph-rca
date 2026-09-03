import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def load_fault_scenarios(scenarios_dir=None, only_executable=True):
    """
    Load fault scenarios from JSON files in a specified directory.

    参数：
        scenarios_dir (str or Path, optional): Path to the directory containing fault scenario 
            JSON files. If None, uses the "fault-scenarios" folder relative to this file.
        only_executable (bool, optional): If True, only scenarios with "execute" set to True 
            are included. If False, all scenarios are loaded regardless of their "execute" flag.

    返回：
        list: List of dictionaries, each representing a fault scenario loaded from a JSON file.
              目录不存在或无有效场景时返回空列表。
    """
    if scenarios_dir is None:
        scenarios_dir = Path(__file__).parent / "fault-scenarios"
    else:
        scenarios_dir = Path(scenarios_dir)
    
    logger.info("从以下路径加载故障场景：%s", scenarios_dir.absolute())
    
    if not scenarios_dir.exists():
        logger.error("目录不存在：%s", scenarios_dir)
        return []
    
    scenarios = []
    json_files = sorted(scenarios_dir.glob("*.json"))
    
    for json_file in json_files:
        try:
            with open(json_file, 'r') as f:
                scenario = json.load(f)
                scenario['_source_file'] = json_file.name
                if scenario.get("execute", False) and only_executable:
                    scenarios.append(scenario)
                else:
                    logger.warning(
                        "Scenario %s skipped as user specified",
                        scenario.get("scenario", "unknown") + " - " + scenario.get("fault_type", "unknown")
                    )
                logger.info("已加载场景：%s", json_file.name)
        except json.JSONDecodeError as e:
            logger.error("加载 %s 失败：%s", json_file.name, e)
        except Exception as e:
            logger.exception("Unexpected error with %s: %s", json_file.name, e)
    
    logger.info("共加载场景数：%s", len(scenarios))
    return scenarios