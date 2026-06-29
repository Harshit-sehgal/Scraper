"""Unit tests for ``app.checkpoint_manager`` - world-state checkpointing."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.checkpoint_manager import CheckpointManager, get_checkpoint_manager


@pytest.fixture
def tmp_base() -> Path:
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def manager(tmp_base: Path) -> CheckpointManager:
    return CheckpointManager(str(tmp_base))


@pytest.fixture
def mock_world_state() -> MagicMock:
    ws = MagicMock()
    ws.to_dict.return_value = {"key": "value", "timestamp": 12345}
    return ws


class TestCheckpointManagerInit:
    def test_creates_base_directory(self, tmp_base: Path) -> None:
        sub = tmp_base / "ckpts"
        CheckpointManager(str(sub))
        assert sub.exists()

    def test_base_dir_does_not_exist_creates_it(self, tmp_base: Path) -> None:
        sub = tmp_base / "nested" / "path"
        manager = CheckpointManager(str(sub))
        assert sub.exists()
        assert isinstance(manager, CheckpointManager)


class TestCreateCheckpoint:
    def test_invalid_label_raises_value_error(self, manager: CheckpointManager) -> None:
        with pytest.raises(ValueError, match="Invalid checkpoint label"):
            manager.create_checkpoint(label="")

    def test_label_with_spaces_raises_value_error(self, manager: CheckpointManager) -> None:
        with pytest.raises(ValueError, match="Invalid checkpoint label"):
            manager.create_checkpoint(label="my label")

    def test_creates_checkpoint_file(self, manager: CheckpointManager, mock_world_state) -> None:
        with patch("app.checkpoint_manager.get_world_state", return_value=mock_world_state):
            path = manager.create_checkpoint(label="test")
            assert os.path.exists(path)

    def test_creates_valid_json(self, manager: CheckpointManager, mock_world_state) -> None:
        with patch("app.checkpoint_manager.get_world_state", return_value=mock_world_state):
            path = manager.create_checkpoint(label="test")
            with open(path) as f:
                data = json.load(f)
            assert data == {"key": "value", "timestamp": 12345}

    def test_filename_format(self, manager: CheckpointManager, mock_world_state) -> None:
        with patch("app.checkpoint_manager.get_world_state", return_value=mock_world_state):
            path = manager.create_checkpoint(label="pre_deploy")
            name = os.path.basename(path)
            assert name.startswith("checkpoint_pre_deploy_")
            assert name.endswith(".json")

    def test_label_with_hyphen_and_underscore(self, manager: CheckpointManager, mock_world_state) -> None:
        with patch("app.checkpoint_manager.get_world_state", return_value=mock_world_state):
            path = manager.create_checkpoint(label="pre-deploy_v2")
            assert os.path.exists(path)

    def test_label_with_dots_and_slashes_raises_value_error(self, manager: CheckpointManager, mock_world_state) -> None:
        with patch("app.checkpoint_manager.get_world_state", return_value=mock_world_state):
            with pytest.raises(ValueError, match="Invalid checkpoint label"):
                manager.create_checkpoint(label="../../etc")

    def test_cleans_up_temp_on_failure(self, manager: CheckpointManager, mock_world_state) -> None:
        mock_world_state.to_dict.side_effect = RuntimeError("Boom!")
        with patch("app.checkpoint_manager.get_world_state", return_value=mock_world_state):
            with pytest.raises(RuntimeError, match="Boom!"):
                manager.create_checkpoint(label="test")

    def test_creates_multiple_checkpoints(self, manager: CheckpointManager, mock_world_state) -> None:
        with patch("app.checkpoint_manager.get_world_state", return_value=mock_world_state):
            p1 = manager.create_checkpoint(label="first")
            p2 = manager.create_checkpoint(label="second")
            assert p1 != p2
            assert os.path.exists(p1)
            assert os.path.exists(p2)


class TestLoadCheckpoint:
    def test_loads_checkpoint(self, manager: CheckpointManager, mock_world_state) -> None:
        ws_mock = MagicMock()
        with patch("app.checkpoint_manager.get_world_state", return_value=mock_world_state):
            path = manager.create_checkpoint(label="test")
        mock_world_state.reset_mock()

        with patch("app.checkpoint_manager.get_world_state", return_value=ws_mock):
            manager.load_checkpoint(path)
            ws_mock.from_dict.assert_called_once_with({"key": "value", "timestamp": 12345})

    def test_path_traversal_raises_on_load(self, tmp_base: Path) -> None:
        manager = CheckpointManager(str(tmp_base))
        with pytest.raises(ValueError, match="outside base directory"):
            manager.load_checkpoint("/etc/passwd")

    def test_nonexistent_file_raises(self, manager: CheckpointManager) -> None:
        with pytest.raises(FileNotFoundError):
            manager.load_checkpoint(str(manager.base_dir / "nonexistent.json"))


class TestListCheckpoints:
    def test_empty_when_no_checkpoints(self, manager: CheckpointManager) -> None:
        assert manager.list_checkpoints() == []

    def test_returns_list_of_checkpoints(self, manager: CheckpointManager, mock_world_state) -> None:
        with patch("app.checkpoint_manager.get_world_state", return_value=mock_world_state):
            manager.create_checkpoint(label="a")
            manager.create_checkpoint(label="b")
        checkpoints = manager.list_checkpoints()
        assert len(checkpoints) == 2
        assert all(c["filename"].startswith("checkpoint_") for c in checkpoints)

    def test_ordered_newest_first(self, manager: CheckpointManager, mock_world_state) -> None:
        import time

        with patch("app.checkpoint_manager.get_world_state", return_value=mock_world_state):
            manager.create_checkpoint(label="first")
            time.sleep(0.01)
            manager.create_checkpoint(label="second")
        checkpoints = manager.list_checkpoints()
        assert "second" in checkpoints[0]["filename"]
        assert "first" in checkpoints[1]["filename"]


class TestGetLatestCheckpoint:
    def test_none_when_no_checkpoints(self, manager: CheckpointManager) -> None:
        assert manager.get_latest_checkpoint() is None

    def test_returns_latest_path(self, manager: CheckpointManager, mock_world_state) -> None:
        import time

        with patch("app.checkpoint_manager.get_world_state", return_value=mock_world_state):
            manager.create_checkpoint(label="older")
            time.sleep(0.01)
            latest = manager.create_checkpoint(label="latest")
        assert manager.get_latest_checkpoint() == latest


class TestGetCheckpointManager:
    def test_returns_singleton(self) -> None:
        with patch("app.checkpoint_manager.settings") as mock_settings:
            mock_settings.DATA_DIR = "/tmp"
            m1 = get_checkpoint_manager()
            m2 = get_checkpoint_manager()
            assert m1 is m2

    def test_resets_on_reimport(self) -> None:
        with patch("app.checkpoint_manager.settings") as mock_settings:
            mock_settings.DATA_DIR = "/tmp"
            m1 = get_checkpoint_manager()
            assert m1 is not None
