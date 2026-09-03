#!/usr/bin/env python3
"""
CLI tool for bulk editing JSON configurations for agent configs and fault scenarios.

Allows users to:
1. Select all configurations from a specific testbed/app (e.g., Hotel Reservation, Social Network)
2. Manually select individual configurations
3. Toggle the "execute" flag for configurations

This tool can be used standalone or before running automated_experiment.py
"""

import json
import logging
from pathlib import Path
from typing import Optional

import click

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


class ConfigurationEditor:
    """基于 CLI 批量编辑配置 JSON 文件的编辑器。"""

    def __init__(self, agents_dir: Optional[Path] = None, scenarios_dir: Optional[Path] = None):
        """
        Initialize the configuration editor.

        参数：
            agents_dir: Directory containing agent configuration JSON files.
                       Defaults to "<this_module>/agent-configurations".
            scenarios_dir: Directory containing fault scenario JSON files.
                          Defaults to "<this_module>/fault-scenarios".
        """
        if agents_dir is None:
            agents_dir = Path(__file__).parent / "agent-configurations"
        else:
            agents_dir = Path(agents_dir)

        if scenarios_dir is None:
            scenarios_dir = Path(__file__).parent / "fault-scenarios"
        else:
            scenarios_dir = Path(scenarios_dir)

        self.agents_dir = agents_dir
        self.scenarios_dir = scenarios_dir

        # 加载配置和场景
        self.agent_configs = self._load_json_files(self.agents_dir)
        self.scenarios = self._load_json_files(self.scenarios_dir)

        logger.info(f"Loaded {len(self.agent_configs)} agent configurations from {self.agents_dir}")
        logger.info(f"Loaded {len(self.scenarios)} fault scenarios from {self.scenarios_dir}")

    def _load_json_files(self, directory: Path) -> dict:
        """
        Load all JSON files from a directory.

        参数：
            directory: Directory containing JSON files.

        返回：
            Dictionary mapping filename -> (config_dict, file_path)
        """
        configs = {}
        if not directory.exists():
            logger.error(f"Directory not found: {directory}")
            return configs

        for json_file in sorted(directory.glob("*.json")):
            try:
                with open(json_file, "r") as f:
                    config = json.load(f)
                    configs[json_file.name] = (config, json_file)
            except json.JSONDecodeError as e:
                logger.error(f"加载 {json_file.name} 失败：{e}")
            except Exception as e:
                logger.error(f"Unexpected error loading {json_file.name}: {e}")

        return configs

    def display_agent_configs(self) -> None:
        """展示全部 Agent 配置及 execute 状态（以 agent id 为索引）。"""
        print("\n" + "=" * 80)
        print("AGENT CONFIGURATIONS")
        print("=" * 80)
        for filename, (config, _) in self.agent_configs.items():
            name = config.get("name", "Unknown")
            agent_id = config.get("id", "Unknown")
            execute = "✓" if config.get("execute", False) else "✗"
            print(f"{agent_id}. [{execute}] {agent_id} - {name:40s} ({filename})")

    def display_scenarios(self) -> None:
        """展示全部故障场景及 execute 状态。"""
        print("\n" + "=" * 80)
        print("FAULT SCENARIOS")
        print("=" * 80)
        for idx, (filename, (scenario, _)) in enumerate(self.scenarios.items(), 1):
            app = scenario.get("app_name", scenario.get("scenario", "Unknown"))
            fault = scenario.get("fault_type", "Unknown")
            execute = "✓" if scenario.get("execute", False) else "✗"
            print(
                f"{idx:2d}. [{execute}] {app:30s} - {fault:30s} ({filename})"
            )

    def get_unique_apps(self) -> dict:
        """
        从场景配置中提取唯一应用名。

        返回：
            Dictionary mapping lowercase app name -> list of filenames
        """
        apps = {}
        for filename, (scenario, _) in self.scenarios.items():
            app = scenario.get("app_name", scenario.get("scenario", "Unknown")).lower()
            if app not in apps:
                apps[app] = []
            apps[app].append(filename)
        return apps

    def set_scenarios_by_app(self, app_name: str, execute: bool) -> int:
        """
        Set the execute flag for all scenarios belonging to a specific application.

        参数：
            app_name: Application name (case-insensitive).
            execute: Whether to enable or disable execution.

        返回：
            Number of scenarios modified.
        """
        app_name_lower = app_name.lower()
        modified_count = 0

        for filename, (scenario, filepath) in self.scenarios.items():
            scenario_app = scenario.get("app_name", scenario.get("scenario", "Unknown")).lower()
            if scenario_app == app_name_lower:
                if scenario.get("execute") != execute:
                    scenario["execute"] = execute
                    self._save_json_file(filepath, scenario)
                    modified_count += 1

        return modified_count

    def set_agent_config(self, config_id: str, execute: bool) -> bool:
        """
        Set the execute flag for a specific agent configuration.

        参数：
            config_id: Configuration ID or filename.
            execute: Whether to enable or disable execution.

        返回：
            True if configuration was modified, False otherwise.
        """
        for filename, (config, filepath) in self.agent_configs.items():
            if filename == config_id or config.get("id") == config_id or config.get("name") == config_id:
                if config.get("execute") != execute:
                    config["execute"] = execute
                    self._save_json_file(filepath, config)
                    return True
        return False

    def set_scenario(self, scenario_id: str, execute: bool) -> bool:
        """
        Set the execute flag for a specific scenario.

        参数：
            scenario_id: Filename or scenario identifier.
            execute: Whether to enable or disable execution.

        返回：
            True if scenario was modified, False otherwise.
        """
        for filename, (scenario, filepath) in self.scenarios.items():
            if filename == scenario_id:
                if scenario.get("execute") != execute:
                    scenario["execute"] = execute
                    self._save_json_file(filepath, scenario)
                    return True
        return False

    def set_all_agents(self, execute: bool) -> int:
        """
        Set the execute flag for all agent configurations.

        参数：
            execute: Whether to enable or disable execution.

        返回：
            Number of configurations modified.
        """
        modified_count = 0
        for filename, (config, filepath) in self.agent_configs.items():
            if config.get("execute") != execute:
                config["execute"] = execute
                self._save_json_file(filepath, config)
                modified_count += 1
        return modified_count

    def set_all_scenarios(self, execute: bool) -> int:
        """
        Set the execute flag for all fault scenarios.

        参数：
            execute: Whether to enable or disable execution.

        返回：
            Number of scenarios modified.
        """
        modified_count = 0
        for filename, (scenario, filepath) in self.scenarios.items():
            if scenario.get("execute") != execute:
                scenario["execute"] = execute
                self._save_json_file(filepath, scenario)
                modified_count += 1
        return modified_count

    def _save_json_file(self, filepath: Path, data: dict) -> None:
        """
        Save JSON data to a file with proper formatting.

        参数：
            filepath: Path to the JSON file.
            data: Dictionary to save.
        """
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=4)
            logger.info(f"Saved {filepath.name}")
        except Exception as e:
            logger.error(f"保存 {filepath.name} 失败：{e}")



    def _apply_manual_selection(
        self, user_input: str, configs: dict, config_type: str
    ) -> None:
        """
        Apply manual selection with toggle logic.

        参数：
            user_input: Comma-separated numbers with optional +/- prefix.
            configs: Dictionary of configurations.
            config_type: Type of configuration (for display).
        """
        items = list(configs.items())
        modified_count = 0

        # 解析输入
        selections = [s.strip() for s in user_input.split(",")]
        for selection in selections:
            # 检查是否带有 +/- 前缀
            action = None  # None means toggle
            if selection.startswith("+"):
                action = True
                selection = selection[1:].strip()
            elif selection.startswith("-"):
                action = False
                selection = selection[1:].strip()

            try:
                idx = int(selection) - 1
                if 0 <= idx < len(items):
                    filename, (config, filepath) = items[idx]
                    current_state = config.get("execute", False)

                    # 确定新的状态
                    if action is None:  # Toggle
                        new_state = not current_state
                    else:
                        new_state = action

                    if current_state != new_state:
                        config["execute"] = new_state
                        self._save_json_file(filepath, config)
                        modified_count += 1
                        state_str = "enabled" if new_state else "disabled"
                        click.echo(f"  ✓ {filename} - {state_str}")
                else:
                    click.echo(f"  ✗ Invalid index: {idx + 1}")
            except ValueError:
                click.echo(f"  ✗ Invalid input: {selection}")

        click.echo(f"\n✓ Modified {modified_count} {config_type}")

    def _get_scenario_by_filename(self, filename: str) -> tuple[str, dict, Path]:
        """
        按文件名获取场景。

        参数：
            filename: Name of the scenario file.

        返回：
            Tuple of (filename, scenario_dict, filepath)
        """
        if filename in self.scenarios:
            scenario, filepath = self.scenarios[filename]
            return filename, scenario, filepath
        raise ValueError(f"Scenario not found: {filename}")


# ============================================================================
# Click 命令行命令
# ============================================================================

_editor_context: dict = {"agents_dir": None, "scenarios_dir": None}


def get_editor():
    """获取或创建 ConfigurationEditor 实例。"""
    return ConfigurationEditor(
        agents_dir=_editor_context["agents_dir"],
        scenarios_dir=_editor_context["scenarios_dir"],
    )


@click.group()
@click.option(
    "--agents-dir",
    type=click.Path(exists=True),
    default=None,
    help="Directory containing agent configuration JSON files",
)
@click.option(
    "--scenarios-dir",
    type=click.Path(exists=True),
    default=None,
    help="Directory containing fault scenario JSON files",
)
def cli(agents_dir, scenarios_dir):
    """实验配置管理 CLI。"""
    _editor_context["agents_dir"] = Path(agents_dir) if agents_dir else None
    _editor_context["scenarios_dir"] = Path(scenarios_dir) if scenarios_dir else None


@cli.command()
def view_agents():
    """查看全部 Agent 配置。"""
    editor = get_editor()
    click.echo("\n" + "=" * 80)
    click.echo("AGENT CONFIGURATIONS")
    click.echo("=" * 80)
    for idx, (filename, (config, _)) in enumerate(editor.agent_configs.items(), 1):
        name = config.get("name", "Unknown")
        agent_id = config.get("id", "Unknown")
        execute = "✓" if config.get("execute", False) else "✗"
        click.echo(f"{idx:2d}. [{execute}] {agent_id} - {name:40s} ({filename})")


@cli.command()
def view_scenarios():
    """查看全部故障场景。"""
    editor = get_editor()
    click.echo("\n" + "=" * 80)
    click.echo("FAULT SCENARIOS")
    click.echo("=" * 80)
    for idx, (filename, (scenario, _)) in enumerate(editor.scenarios.items(), 1):
        app = scenario.get("app_name", scenario.get("scenario", "Unknown"))
        fault = scenario.get("fault_type", "Unknown")
        execute = "✓" if scenario.get("execute", False) else "✗"
        click.echo(
            f"{idx:2d}. [{execute}] {app:30s} - {fault:30s} ({filename})"
        )


@cli.command()
@click.option("--enable", is_flag=True, help="Enable all agent configurations")
@click.option("--disable", is_flag=True, help="Disable all agent configurations")
def agents(enable, disable):
    """管理全部 Agent 配置。"""
    editor = get_editor()
    
    if enable:
        modified = editor.set_all_agents(True)
        click.secho(f"✓ Enabled {modified} agent configuration(s)", fg="green")
    elif disable:
        modified = editor.set_all_agents(False)
        click.secho(f"✓ Disabled {modified} agent configuration(s)", fg="green")
    else:
        click.echo("Use --enable or --disable")


@cli.command()
@click.option("--enable", is_flag=True, help="Enable all fault scenarios")
@click.option("--disable", is_flag=True, help="Disable all fault scenarios")
def scenarios(enable, disable):
    """管理全部故障场景。"""
    editor = get_editor()
    
    if enable:
        modified = editor.set_all_scenarios(True)
        click.secho(f"✓ Enabled {modified} fault scenario(s)", fg="green")
    elif disable:
        modified = editor.set_all_scenarios(False)
        click.secho(f"✓ Disabled {modified} fault scenario(s)", fg="green")
    else:
        click.echo("Use --enable or --disable")


@cli.command()
@click.option("--enable", type=str, help="Enable all scenarios for this app (case-insensitive)")
@click.option("--disable", type=str, help="Disable all scenarios for this app (case-insensitive)")
@click.option("--list", "list_apps", is_flag=True, help="List all available applications")
def app(enable, disable, list_apps):
    """按应用/测试床管理场景。"""
    editor = get_editor()
    
    if list_apps:
        apps = editor.get_unique_apps()
        click.echo("\n" + "=" * 80)
        click.echo("AVAILABLE APPLICATIONS/TESTBEDS")
        click.echo("=" * 80)
        for app_name in sorted(apps.keys()):
            count = len(apps[app_name])
            click.echo(f"  • {app_name.title()}: {count} scenarios")
        return
    
    if enable:
        modified = editor.set_scenarios_by_app(enable, True)
        click.secho(
            f"✓ Enabled {modified} scenario(s) for {enable.title()}",
            fg="green"
        )
    elif disable:
        modified = editor.set_scenarios_by_app(disable, False)
        click.secho(
            f"✓ Disabled {modified} scenario(s) for {disable.title()}",
            fg="green"
        )
    else:
        click.echo("Use --enable, --disable, or --list")


@cli.command()
@click.option(
    "--type",
    "config_type",
    type=click.Choice(["agents", "scenarios"], case_sensitive=False),
    required=True,
    help="Type of configurations to manage",
)
@click.option("--indices", type=str, help="Comma-separated indices (e.g., 1,3,5)")
def select(config_type, indices):
    """手动选择要启用/禁用的配置。

    使用 + 前缀启用，- 前缀禁用，无前缀则切换。
    示例：'+1,2,-3' 表示启用 1 和 2，禁用 3。
    """
    editor = get_editor()
    
    if not indices:
        click.echo("请提供 --indices 参数")
        return
    
    if config_type.lower() == "agents":
        editor._apply_manual_selection(indices, editor.agent_configs, "agent configurations")
    else:
        editor._apply_manual_selection(indices, editor.scenarios, "scenarios")


def main():
    """CLI 工具主入口。"""
    cli()


if __name__ == "__main__":
    main()
