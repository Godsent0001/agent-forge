import json
import os
from pathlib import Path
import pytest

from app.tools.character import (
    CharacterAssetManagerTool,
    CharacterDesignerTool,
    CharacterPreviewTool,
    CharacterRigTool,
)
from app.tools.graphics import PropDesignerTool, VisualAssetManagerTool
from app.tools.registry import build_tool
from app.tools.scene import EnvironmentDesignerTool


@pytest.mark.asyncio
async def test_character_designer_and_asset_manager(tmp_path):
    char_dir = str(tmp_path / "characters")
    designer = CharacterDesignerTool(characters_dir=char_dir)

    # 1. Create character Julian
    julian_input = json.dumps({
        "name": "Julian",
        "gender": "male",
        "age": 35,
        "height": "tall",
        "body_build": "athletic",
        "skin_tone": "dark Nigerian",
        "hair": "bald",
        "clothing": "navy three-piece suit",
        "accessories": ["glasses"],
        "distinctive_features": ["trimmed beard"],
        "visual_style": "2D vector/cartoon",
    })

    res_str = await designer.execute(julian_input, context=None)
    res = json.loads(res_str)

    assert res["character_id"] == "julian"
    assert res["status"] == "created"
    assert os.path.exists(res["profile_path"])
    assert os.path.exists(res["asset_path"])
    assert os.path.exists(res["preview_path"])

    # 2. Character Asset Manager lookup
    manager = CharacterAssetManagerTool(characters_dir=char_dir)
    get_res_str = await manager.execute(json.dumps({"action": "get", "character_id": "julian"}), context=None)
    get_res = json.loads(get_res_str)

    assert get_res["character_id"] == "julian"
    assert get_res["profile"]["name"] == "Julian"
    assert get_res["profile"]["clothing"] == "navy three-piece suit"

    # List characters
    list_res_str = await manager.execute(json.dumps({"action": "list"}), context=None)
    list_res = json.loads(list_res_str)
    assert list_res["count"] == 1
    assert list_res["characters"][0]["character_id"] == "julian"


@pytest.mark.asyncio
async def test_character_preview_and_rig(tmp_path):
    char_dir = str(tmp_path / "characters")
    out_dir = str(tmp_path / "output")

    # Create character
    designer = CharacterDesignerTool(characters_dir=char_dir)
    await designer.execute(json.dumps({
        "name": "Elara",
        "skin_tone": "fair",
        "hair": "long blonde ponytail",
        "clothing": "red blazer",
    }), context=None)

    # Preview
    preview_tool = CharacterPreviewTool(characters_dir=char_dir)
    preview_out = os.path.join(out_dir, "elara_preview.png")
    prev_res_str = await preview_tool.execute(json.dumps({
        "character_id": "elara",
        "expression": "skeptical",
        "pose": "cross_arms",
        "output_path": preview_out,
    }), context=None)
    prev_res = json.loads(prev_res_str)

    assert prev_res["character_id"] == "elara"
    assert prev_res["expression"] == "skeptical"
    assert os.path.exists(preview_out)

    # Rig
    rig_tool = CharacterRigTool(characters_dir=char_dir)
    rig_out = os.path.join(out_dir, "elara_rig.png")
    rig_res_str = await rig_tool.execute(json.dumps({
        "character_id": "elara",
        "expression": "confident",
        "gesture": "point",
        "output_image_path": rig_out,
    }), context=None)
    rig_res = json.loads(rig_res_str)

    assert rig_res["character_id"] == "elara"
    assert rig_res["character_name"] == "Elara"
    assert os.path.exists(rig_out)


@pytest.mark.asyncio
async def test_environment_and_prop_designers(tmp_path):
    env_dir = str(tmp_path / "environments")
    prop_dir = str(tmp_path / "props")

    # Environment Designer
    env_tool = EnvironmentDesignerTool(environments_dir=env_dir)
    env_res_str = await env_tool.execute(json.dumps({
        "name": "Presidential Debate Stage",
        "type": "presidential_stage",
        "lighting_preset": "dramatic",
    }), context=None)
    env_res = json.loads(env_res_str)

    assert env_res["environment_id"] == "presidential_debate_stage"
    assert os.path.exists(env_res["metadata_path"])
    assert os.path.exists(env_res["asset_path"])

    # Prop Designer
    prop_tool = PropDesignerTool(props_dir=prop_dir)
    prop_res_str = await prop_tool.execute(json.dumps({
        "name": "Debate Podium",
        "kind": "podium",
        "material": "mahogany wood",
    }), context=None)
    prop_res = json.loads(prop_res_str)

    assert prop_res["prop_id"] == "debate_podium"
    assert os.path.exists(prop_res["metadata_path"])
    assert os.path.exists(prop_res["asset_path"])


@pytest.mark.asyncio
async def test_visual_asset_manager(tmp_path):
    assets_root = str(tmp_path / "assets")

    # Create character, environment, prop under assets_root
    char_tool = CharacterDesignerTool(characters_dir=f"{assets_root}/characters")
    await char_tool.execute(json.dumps({"name": "Julian"}), context=None)

    env_tool = EnvironmentDesignerTool(environments_dir=f"{assets_root}/environments")
    await env_tool.execute(json.dumps({"name": "Main Stage"}), context=None)

    prop_tool = PropDesignerTool(props_dir=f"{assets_root}/props")
    await prop_tool.execute(json.dumps({"name": "Microphone"}), context=None)

    # Manager
    manager = VisualAssetManagerTool(assets_dir=assets_root)

    # List all
    list_str = await manager.execute(json.dumps({"action": "list"}), context=None)
    list_res = json.loads(list_str)
    assert "julian" in list_res["assets"]["characters"]
    assert "main_stage" in list_res["assets"]["environments"]
    assert "microphone" in list_res["assets"]["props"]

    # Get by ID
    get_julian = json.loads(await manager.execute(json.dumps({"action": "get", "asset_id": "julian"}), context=None))
    assert get_julian["category"] == "characters"
    assert get_julian["metadata"]["name"] == "Julian"

    get_stage = json.loads(await manager.execute(json.dumps({"action": "get", "asset_id": "main_stage"}), context=None))
    assert get_stage["category"] == "environments"


def test_registry_tool_building():
    char_des = build_tool("character_designer", {})
    assert char_des.name == "character_designer"

    char_prev = build_tool("character_preview", {})
    assert char_prev.name == "character_preview"

    env_des = build_tool("environment_designer", {})
    assert env_des.name == "environment_designer"

    prop_des = build_tool("prop_designer", {})
    assert prop_des.name == "prop_designer"
