"""
Automated Datagraph Management for Experiments

This module handles updating the Neo4j service graph (datagraph) based on the scenario being tested.
It maps scenario names to their corresponding datagraph configuration files and manages the
drop/recreate process.
"""

import logging
import os
import sys
from pathlib import Path

# 将 MCP-server 加入路径，以便导入 DataGraph
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "MCP-server")))
from api.datagraph import DataGraph

logger = logging.getLogger(__name__)

# 场景名称到 datagraph 配置文件的映射
SCENARIO_DATAGRAPH_MAP = {
    "hotel reservation": "hotel-reservation-datagraph.txt",
    "astronomy shop" : "astronomy-shop-datagraph.txt",
    "social network" : "social-network-datagraph.txt"
}

# 存放 datagraph 配置文件的目录
DATAGRAPH_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "MCP-server" / "service-graph"


def update_datagraph_for_scenario(scenario_name: str):
    """
    Updates the Neo4j datagraph for a given scenario.
    
    This function:
    1. Maps the scenario name to its corresponding datagraph config file
    2. Connects to Neo4j
    3. Drops the existing datagraph
    4. Creates a new datagraph from the config file
    
    参数：
        scenario_name (str): Name of the scenario to update the datagraph for.
                           Should match keys in SCENARIO_DATAGRAPH_MAP.
    
    Raises:
        Exception: If datagraph update fails for any reason.
    """
    # 将场景名标准化为小写，便于匹配
    scenario_key = scenario_name.lower()
    
    if scenario_key not in SCENARIO_DATAGRAPH_MAP:
        logger.warning(f"No datagraph mapping found for scenario '{scenario_name}'. Skipping datagraph update.")
        return
    
    config_file = SCENARIO_DATAGRAPH_MAP[scenario_key]
    config_path = DATAGRAPH_CONFIG_DIR / config_file
    
    if not config_path.exists():
        logger.error(f"Datagraph config file not found: {config_path}")
        return
    
    try:
        logger.info(f"Updating datagraph for scenario '{scenario_name}' using {config_file}")
        
        # 初始化 DataGraph 连接
        dg = DataGraph()
        
        # 删除现有 datagraph
        logger.info("正在清空现有 Datagraph...")
        dg.drop_datagraph(confirmation=True)
        
        # 根据配置文件创建新的 datagraph
        logger.info(f"Creating datagraph from {config_path}")
        dg.create_datagraph(str(config_path))
        
        # 关闭连接
        dg.close()
        
        logger.info(f"Successfully updated datagraph for scenario '{scenario_name}'")
        
    except Exception as e:
        logger.error(f"更新场景 '{scenario_name}' 的 Datagraph 失败：{e}")
        raise
