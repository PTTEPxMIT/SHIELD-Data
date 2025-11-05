import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from shield_data.data_upload_handler import (
    DEFAULT_BATCH_DELAY,
    Handler,
    upload_data_from_folder,
)


def write_json(path: Path, content: dict):
    """Helper to write JSON files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content), encoding="utf-8")


# Tests for upload_data_from_folder validation


def test_upload_data_from_folder_raises_for_missing_folder(tmp_path: Path):
    """Test that upload_data_from_folder raises FileNotFoundError for missing folder.

    The function should validate that the results folder exists before attempting
    to monitor it, failing fast with a clear error if the path doesn't exist.
    """
    with pytest.raises(FileNotFoundError):
        upload_data_from_folder(str(tmp_path / "does_not_exist"))


def test_upload_data_from_folder_raises_for_file_path(tmp_path: Path):
    """Test that upload_data_from_folder raises NotADirectoryError for file paths.

    If the provided path points to a regular file instead of a directory, the
    function should raise NotADirectoryError to prevent monitoring errors.
    """
    file_path = tmp_path / "file.txt"
    file_path.write_text("test")
    with pytest.raises(NotADirectoryError):
        upload_data_from_folder(str(file_path))


def test_upload_data_from_folder_raises_when_batch_delay_too_large(tmp_path: Path):
    """Test that batch_delay must be less than check_interval.

    If batch_delay is greater than or equal to check_interval, events could
    be lost or batching wouldn't work correctly. This validates the timing
    constraints are enforced.
    """
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    with pytest.raises(ValueError, match=r"batch_delay.*must be less than"):
        upload_data_from_folder(str(results_dir), check_interval=5, batch_delay=5)


def test_upload_data_from_folder_accepts_valid_timing(tmp_path: Path):
    """Test that valid timing parameters are accepted.

    When batch_delay < check_interval, the validation should pass and the
    observer setup should begin (though we'll interrupt it immediately).
    """
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    with patch("shield_data.data_upload_handler.Observer") as mock_observer:
        mock_obs_instance = Mock()
        mock_observer.return_value = mock_obs_instance

        # Simulate immediate interrupt
        def side_effect(*args):
            raise KeyboardInterrupt()

        mock_obs_instance.start.side_effect = side_effect

        try:
            upload_data_from_folder(str(results_dir), check_interval=10, batch_delay=3)
        except KeyboardInterrupt:
            pass

        # Verify observer was created and scheduled
        mock_observer.assert_called_once()
        mock_obs_instance.schedule.assert_called_once()


# Tests for Handler initialization


def test_handler_init_sets_results_folder():
    """Test that Handler constructor sets results_folder attribute.

    The results_folder is used throughout the handler for path resolution
    and should be correctly stored from the constructor argument.
    """
    handler = Handler(results_folder="my_results")
    assert handler.results_folder == "my_results"


def test_handler_init_sets_batch_delay():
    """Test that Handler constructor sets custom batch_delay.

    Custom batch_delay allows tuning the debounce time for file events,
    and should be correctly stored from the constructor argument.
    """
    handler = Handler(batch_delay=5.0)
    assert handler.batch_delay == 5.0


def test_handler_init_uses_default_batch_delay():
    """Test that Handler uses DEFAULT_BATCH_DELAY when not specified.

    If no batch_delay is provided, the handler should use the module-level
    default to ensure consistent behavior.
    """
    handler = Handler()
    assert handler.batch_delay == DEFAULT_BATCH_DELAY


def test_handler_init_sets_current_branch_to_none():
    """Test that Handler starts with no current branch.

    The current_branch tracks the git branch for the upload session and
    should be None initially until the first batch is processed.
    """
    handler = Handler()
    assert handler.current_branch is None


def test_handler_init_sets_empty_pending_changes():
    """Test that Handler starts with empty pending_changes set.

    The pending_changes set accumulates file events between batches and
    should start empty.
    """
    handler = Handler()
    assert handler.pending_changes == set()


def test_handler_init_sets_empty_session_files():
    """Test that Handler starts with empty session_files set.

    The session_files set tracks all files processed in the current session
    and should start empty.
    """
    handler = Handler()
    assert handler.session_files == set()


def test_handler_init_sets_timer_to_none():
    """Test that Handler starts with no active timer.

    The timer is used for batching events and should be None initially
    until the first event triggers it.
    """
    handler = Handler()
    assert handler.timer is None


# Tests for parse_run_info


def test_parse_run_info_extracts_run_folder_from_path(tmp_path: Path):
    """Test that parse_run_info correctly identifies run folder from path.

    The run folder follows the format YY.MM.DD_run_X_HHhMM and must be
    extracted from the file path to identify which run the data belongs to.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    write_json(
        metadata_path,
        {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
    )

    handler = Handler(results_folder=str(results_dir))
    file_paths = {str(results_dir / run_folder / "data.csv")}

    result = handler.parse_run_info(file_paths)
    assert result["run_folder"] == run_folder


def test_parse_run_info_raises_for_missing_run_folder_format(tmp_path: Path):
    """Test that parse_run_info raises ValueError for invalid folder structure.

    If no folder in the path matches the expected YY.MM.DD_run_X_HHhMM format,
    the function should raise ValueError with a clear message about the
    expected format.
    """
    results_dir = tmp_path / "results"
    handler = Handler(results_folder=str(results_dir))
    file_paths = {str(results_dir / "invalid_folder" / "data.csv")}

    with pytest.raises(ValueError, match=r"Run folder.*not found"):
        handler.parse_run_info(file_paths)


def test_parse_run_info_raises_for_missing_metadata_file(tmp_path: Path):
    """Test that parse_run_info raises FileNotFoundError for missing metadata.

    Each run must have a run_metadata.json file. If it's missing, the function
    should raise FileNotFoundError to indicate incomplete run data.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    handler = Handler(results_folder=str(results_dir))
    file_paths = {str(results_dir / run_folder / "data.csv")}

    with pytest.raises(FileNotFoundError, match="Metadata file does not exist"):
        handler.parse_run_info(file_paths)


def test_parse_run_info_raises_for_invalid_json(tmp_path: Path):
    """Test that parse_run_info raises ValueError for malformed JSON.

    If run_metadata.json contains invalid JSON, the function should raise
    ValueError with details about the JSON parsing error.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text("{invalid json}", encoding="utf-8")

    handler = Handler(results_folder=str(results_dir))
    file_paths = {str(results_dir / run_folder / "data.csv")}

    with pytest.raises(ValueError, match="Invalid JSON"):
        handler.parse_run_info(file_paths)


def test_parse_run_info_raises_for_missing_run_info_section(tmp_path: Path):
    """Test that parse_run_info raises KeyError when 'run_info' is missing.

    The metadata must contain a 'run_info' section with the run parameters.
    If missing, raise KeyError to indicate invalid metadata structure.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    write_json(metadata_path, {"other_data": "value"})

    handler = Handler(results_folder=str(results_dir))
    file_paths = {str(results_dir / run_folder / "data.csv")}

    with pytest.raises(KeyError, match="run_info"):
        handler.parse_run_info(file_paths)


@pytest.mark.parametrize("missing_field", ["run_type", "date", "furnace_setpoint"])
def test_parse_run_info_raises_for_missing_required_field(
    tmp_path: Path, missing_field: str
):
    """Test that parse_run_info raises KeyError for missing required fields.

    The run_info section must contain run_type, date, and furnace_setpoint.
    Each field is tested individually to ensure all are validated.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    # Create metadata with all fields except the one being tested
    run_info = {
        "run_type": "baseline",
        "date": "2024-11-05",
        "furnace_setpoint": 1273,
    }
    del run_info[missing_field]

    write_json(metadata_path, {"run_info": run_info})

    handler = Handler(results_folder=str(results_dir))
    file_paths = {str(results_dir / run_folder / "data.csv")}

    with pytest.raises(KeyError, match=missing_field):
        handler.parse_run_info(file_paths)


def test_parse_run_info_returns_correct_total_files(tmp_path: Path):
    """Test that parse_run_info counts the number of files in the batch.

    The total_files count is used in PR descriptions and should accurately
    reflect the number of file paths provided.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    write_json(
        metadata_path,
        {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
    )

    handler = Handler(results_folder=str(results_dir))
    file_paths = {
        str(results_dir / run_folder / "data1.csv"),
        str(results_dir / run_folder / "data2.csv"),
        str(results_dir / run_folder / "data3.csv"),
    }

    result = handler.parse_run_info(file_paths)
    assert result["total_files"] == 3


def test_parse_run_info_returns_metadata_dict(tmp_path: Path):
    """Test that parse_run_info returns the full metadata dictionary.

    The metadata is used for PR content generation and should be included
    in the return value for downstream processing.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    metadata = {
        "run_info": {
            "run_type": "baseline",
            "date": "2024-11-05",
            "furnace_setpoint": 1273,
        }
    }
    write_json(metadata_path, metadata)

    handler = Handler(results_folder=str(results_dir))
    file_paths = {str(results_dir / run_folder / "data.csv")}

    result = handler.parse_run_info(file_paths)
    assert result["metadata"] == metadata


# Tests for create_pr_content


def test_create_pr_content_returns_title_and_body():
    """Test that create_pr_content returns a tuple of (title, body).

    The function generates both PR title and body text, which should be
    returned as a tuple for separate use in PR creation.
    """
    handler = Handler()
    run_info = {
        "run_folder": "24.11.05_run_1_14h30",
        "metadata": {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
        "total_files": 5,
    }

    title, body = handler.create_pr_content(run_info)
    assert isinstance(title, str)
    assert isinstance(body, str)


def test_create_pr_content_title_includes_run_type():
    """Test that PR title includes the run_type.

    The run type is a key piece of information and should appear in the
    PR title for easy identification in the PR list.
    """
    handler = Handler()
    run_info = {
        "run_folder": "24.11.05_run_1_14h30",
        "metadata": {
            "run_info": {
                "run_type": "permeation_test",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
        "total_files": 5,
    }

    title, _ = handler.create_pr_content(run_info)
    assert "permeation_test" in title


def test_create_pr_content_title_includes_date():
    """Test that PR title includes the run date.

    The date helps chronologically organize PRs and should be included
    in the title.
    """
    handler = Handler()
    run_info = {
        "run_folder": "24.11.05_run_1_14h30",
        "metadata": {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
        "total_files": 5,
    }

    title, _ = handler.create_pr_content(run_info)
    assert "2024-11-05" in title


def test_create_pr_content_title_includes_setpoint():
    """Test that PR title includes the furnace setpoint with units.

    The furnace setpoint is a critical experimental parameter and should
    appear in the title with the temperature unit (K).
    """
    handler = Handler()
    run_info = {
        "run_folder": "24.11.05_run_1_14h30",
        "metadata": {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
        "total_files": 5,
    }

    title, _ = handler.create_pr_content(run_info)
    assert "1273" in title
    assert "K" in title


def test_create_pr_content_body_includes_metadata():
    """Test that PR body includes the metadata JSON.

    The full metadata should be included in the PR body for reference
    and documentation of experimental conditions.
    """
    handler = Handler()
    run_info = {
        "run_folder": "24.11.05_run_1_14h30",
        "metadata": {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
        "total_files": 5,
    }

    _, body = handler.create_pr_content(run_info)
    assert "run_type" in body
    assert "baseline" in body
    assert "1273" in body


# Tests for on_any_event


def test_on_any_event_ignores_directory_events():
    """Test that on_any_event ignores directory creation/modification events.

    Only file events should trigger data upload processing. Directory events
    should be ignored to avoid unnecessary processing.
    """
    handler = Handler(results_folder="results")
    event = Mock()
    event.is_directory = True
    event.src_path = "results/some_dir"

    handler.on_any_event(event)

    assert len(handler.pending_changes) == 0


def test_on_any_event_ignores_backup_folder_files():
    """Test that files in backup folders are ignored.

    Backup folders contain historical data that shouldn't trigger new PRs.
    Files in any 'backup' subfolder should be filtered out.
    """
    handler = Handler(results_folder="results")
    event = Mock()
    event.is_directory = False
    event.src_path = "results/backup/old_data.csv"

    handler.on_any_event(event)

    assert len(handler.pending_changes) == 0


def test_on_any_event_ignores_catalogue_csv():
    """Test that runs_catalogue.csv is ignored.

    The catalogue is auto-generated by the handler itself and shouldn't
    trigger additional processing to avoid infinite loops.
    """
    handler = Handler(results_folder="results")
    event = Mock()
    event.is_directory = False
    event.src_path = "results/run_data/runs_catalogue.csv"

    handler.on_any_event(event)

    assert len(handler.pending_changes) == 0


def test_on_any_event_ignores_readme():
    """Test that README.md is ignored.

    The README is auto-generated alongside the catalogue and should be
    ignored for the same reasons.
    """
    handler = Handler(results_folder="results")
    event = Mock()
    event.is_directory = False
    event.src_path = "results/run_data/README.md"

    handler.on_any_event(event)

    assert len(handler.pending_changes) == 0


def test_on_any_event_adds_valid_file_to_pending_changes():
    """Test that valid file events are added to pending_changes.

    Regular data files should be tracked in pending_changes for batch
    processing. The relative path from results_folder is stored.
    """
    handler = Handler(results_folder="results")
    event = Mock()
    event.is_directory = False
    event.src_path = "results/24.11.05_run_1_14h30/data.csv"

    with patch("shield_data.data_upload_handler.threading.Timer"):
        handler.on_any_event(event)

    assert len(handler.pending_changes) == 1
    # Check that some form of the relative path is stored (OS-agnostic)
    stored_path = next(iter(handler.pending_changes))
    assert "24.11.05_run_1_14h30" in stored_path
    assert "data.csv" in stored_path


def test_on_any_event_starts_timer():
    """Test that on_any_event starts a batching timer.

    After detecting a file change, a timer should be started to batch
    multiple changes together before processing.
    """
    handler = Handler(results_folder="results", batch_delay=3)
    event = Mock()
    event.is_directory = False
    event.src_path = "results/24.11.05_run_1_14h30/data.csv"

    with patch("shield_data.data_upload_handler.threading.Timer") as mock_timer:
        handler.on_any_event(event)

        # Verify Timer was instantiated with correct delay
        mock_timer.assert_called_once()
        assert mock_timer.call_args[0][0] == 3  # batch_delay
        # Verify the timer was started
        mock_timer.return_value.start.assert_called_once()
    # Clean up
    handler.timer.cancel()


def test_on_any_event_cancels_existing_timer():
    """Test that on_any_event cancels previous timer and starts new one.

    When multiple events occur, the timer should be reset to batch all
    changes together, ensuring the delay is measured from the last event.
    """
    handler = Handler(results_folder="results", batch_delay=3)
    event1 = Mock()
    event1.is_directory = False
    event1.src_path = "results/24.11.05_run_1_14h30/data1.csv"

    with patch("shield_data.data_upload_handler.threading.Timer") as mock_timer:
        # First event creates a timer
        handler.on_any_event(event1)

        # Second event should cancel the first timer
        event2 = Mock()
        event2.is_directory = False
        event2.src_path = "results/24.11.05_run_1_14h30/data2.csv"
        handler.on_any_event(event2)

        # Verify Timer was called twice (once for each event)
        assert mock_timer.call_count == 2
        # Verify cancel was called on the first timer
        mock_timer.return_value.cancel.assert_called()


def test_on_any_event_accumulates_multiple_files():
    """Test that multiple file events accumulate in pending_changes.

    All file changes should be collected together for batch processing,
    not processed individually.
    """
    handler = Handler(results_folder="results")

    with patch("shield_data.data_upload_handler.threading.Timer"):
        for i in range(3):
            event = Mock()
            event.is_directory = False
            event.src_path = f"results/24.11.05_run_1_14h30/data{i}.csv"
            handler.on_any_event(event)

    assert len(handler.pending_changes) == 3


# Tests for process_batch with mocking


def test_process_batch_does_nothing_when_no_pending_changes():
    """Test that process_batch returns early if pending_changes is empty.

    If called with no pending changes (edge case), the function should
    return immediately without attempting git operations.
    """
    handler = Handler(results_folder="results")

    # Should not raise any errors
    handler.process_batch()

    # No branch should be created
    assert handler.current_branch is None


def test_process_batch_creates_new_branch_on_first_call(tmp_path: Path):
    """Test that process_batch creates a new git branch for first session.

    When processing the first batch (no current_branch), a new branch
    should be created with a unique identifier.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    write_json(
        metadata_path,
        {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
    )

    handler = Handler(results_folder=str(results_dir))
    handler.pending_changes.add(f"{run_folder}/data.csv")

    with (
        patch("shield_data.data_upload_handler.subprocess.run") as mock_run,
        patch("shield_data.data_upload_handler.build_catalogue"),
    ):
        # Mock git diff to indicate changes
        mock_run.return_value = Mock(returncode=1)

        handler.process_batch()

    assert handler.current_branch is not None
    assert handler.current_branch.startswith("add_new_data_")


def test_process_batch_calls_build_catalogue(tmp_path: Path):
    """Test that process_batch rebuilds the catalogue before committing.

    The catalogue should be regenerated with each batch to ensure it
    reflects all current runs.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    write_json(
        metadata_path,
        {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
    )

    handler = Handler(results_folder=str(results_dir))
    handler.pending_changes.add(f"{run_folder}/data.csv")

    with (
        patch("shield_data.data_upload_handler.subprocess.run") as mock_run,
        patch("shield_data.data_upload_handler.build_catalogue") as mock_build,
    ):
        mock_run.return_value = Mock(returncode=1)

        handler.process_batch()

    mock_build.assert_called_once_with(str(results_dir))


def test_process_batch_runs_git_checkout_main_for_new_branch(tmp_path: Path):
    """Test that process_batch checks out main before creating new branch.

    When starting a new session, the handler should checkout main as the
    base for the new feature branch.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    write_json(
        metadata_path,
        {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
    )

    handler = Handler(results_folder=str(results_dir))
    handler.pending_changes.add(f"{run_folder}/data.csv")

    with (
        patch("shield_data.data_upload_handler.subprocess.run") as mock_run,
        patch("shield_data.data_upload_handler.build_catalogue"),
    ):
        mock_run.return_value = Mock(returncode=1)

        handler.process_batch()

    # Check that "git checkout main" was called
    checkout_main_calls = [
        call for call in mock_run.call_args_list if "git checkout main" in str(call)
    ]
    assert len(checkout_main_calls) >= 1


def test_process_batch_runs_git_add_on_results_folder(tmp_path: Path):
    """Test that process_batch stages only the results folder.

    Git add should be scoped to the monitored results folder to avoid
    staging unrelated changes in the repository.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    write_json(
        metadata_path,
        {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
    )

    handler = Handler(results_folder=str(results_dir))
    handler.pending_changes.add(f"{run_folder}/data.csv")

    with (
        patch("shield_data.data_upload_handler.subprocess.run") as mock_run,
        patch("shield_data.data_upload_handler.build_catalogue"),
    ):
        mock_run.return_value = Mock(returncode=1)

        handler.process_batch()

    # Check that git add was called with results folder (shell=True commands are strings)
    add_calls = [
        call
        for call in mock_run.call_args_list
        if len(call.args) > 0
        and isinstance(call.args[0], str)
        and "git add" in call.args[0]
    ]
    assert len(add_calls) >= 1
    # Verify the path is included
    assert any(str(results_dir) in call.args[0] for call in add_calls)


def test_process_batch_skips_commit_when_no_changes(tmp_path: Path):
    """Test that process_batch skips commit/push when git diff shows no changes.

    If there are no actual changes to commit (edge case), the handler should
    skip the commit and push operations.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    write_json(
        metadata_path,
        {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
    )

    handler = Handler(results_folder=str(results_dir))
    handler.pending_changes.add(f"{run_folder}/data.csv")

    with (
        patch("shield_data.data_upload_handler.subprocess.run") as mock_run,
        patch("shield_data.data_upload_handler.build_catalogue"),
    ):
        # Mock git diff to indicate NO changes (returncode 0)
        mock_run.return_value = Mock(returncode=0)

        handler.process_batch()

    # Should not have commit or push calls
    commit_calls = [
        call for call in mock_run.call_args_list if "git commit" in str(call)
    ]
    assert len(commit_calls) == 0


def test_process_batch_clears_pending_changes_after_processing(tmp_path: Path):
    """Test that pending_changes is cleared after batch processing.

    After successfully processing a batch, pending_changes should be reset
    to prevent reprocessing the same files.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    write_json(
        metadata_path,
        {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
    )

    handler = Handler(results_folder=str(results_dir))
    handler.pending_changes.add(f"{run_folder}/data.csv")

    with (
        patch("shield_data.data_upload_handler.subprocess.run"),
        patch("shield_data.data_upload_handler.build_catalogue"),
    ):
        handler.process_batch()

    assert len(handler.pending_changes) == 0


def test_process_batch_updates_session_files(tmp_path: Path):
    """Test that session_files is updated with processed files.

    All processed files should be added to session_files to track what's
    been handled in the current upload session.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    write_json(
        metadata_path,
        {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
    )

    handler = Handler(results_folder=str(results_dir))
    file_path = f"{run_folder}/data.csv"
    handler.pending_changes.add(file_path)

    with (
        patch("shield_data.data_upload_handler.subprocess.run"),
        patch("shield_data.data_upload_handler.build_catalogue"),
    ):
        handler.process_batch()

    assert file_path in handler.session_files


def test_process_batch_reuses_branch_on_subsequent_calls(tmp_path: Path):
    """Test that process_batch reuses existing branch for additional updates.

    After the first batch creates a branch, subsequent batches should update
    that same branch rather than creating new ones.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    write_json(
        metadata_path,
        {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
    )

    handler = Handler(results_folder=str(results_dir))
    handler.pending_changes.add(f"{run_folder}/data1.csv")

    with (
        patch("shield_data.data_upload_handler.subprocess.run") as mock_run,
        patch("shield_data.data_upload_handler.build_catalogue"),
    ):
        mock_run.return_value = Mock(returncode=1)

        # First batch
        handler.process_batch()
        first_branch = handler.current_branch

        # Second batch
        handler.pending_changes.add(f"{run_folder}/data2.csv")
        handler.process_batch()
        second_branch = handler.current_branch

    assert first_branch == second_branch


def test_process_batch_skips_commit_when_no_changes_on_existing_branch(
    tmp_path: Path,
):
    """Test that process_batch skips commit when updating existing branch with no changes.

    When updating an existing branch, if git diff shows no changes after
    rebuilding the catalogue, the commit and push should be skipped.
    """
    results_dir = tmp_path / "results"
    run_folder = "24.11.05_run_1_14h30"
    metadata_path = results_dir / run_folder / "run_metadata.json"

    write_json(
        metadata_path,
        {
            "run_info": {
                "run_type": "baseline",
                "date": "2024-11-05",
                "furnace_setpoint": 1273,
            }
        },
    )

    handler = Handler(results_folder=str(results_dir))
    handler.pending_changes.add(f"{run_folder}/data.csv")

    with (
        patch("shield_data.data_upload_handler.subprocess.run") as mock_run,
        patch("shield_data.data_upload_handler.build_catalogue"),
    ):
        # First call creates branch with changes
        mock_run.return_value = Mock(returncode=1)
        handler.process_batch()

        # Second call updates branch but no changes in git diff
        handler.pending_changes.add(f"{run_folder}/data2.csv")

        def mock_subprocess(cmd, **kwargs):
            # Return 0 (no changes) for git diff --cached --quiet
            if "git diff --cached --quiet" in cmd:
                return Mock(returncode=0)
            return Mock(returncode=1)

        mock_run.side_effect = mock_subprocess
        handler.process_batch()

        # Verify commit was NOT called on second batch
        commit_calls = [
            call for call in mock_run.call_args_list if "git commit" in str(call)
        ]
        # Should only have 1 commit (from first batch)
        assert len(commit_calls) == 1


def test_upload_data_from_folder_starts_observer(tmp_path: Path):
    """Test that upload_data_from_folder starts the file system observer.

    The function should create an Observer, schedule the Handler, and
    start monitoring the folder. This tests the setup (not the infinite loop).
    """
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    with (
        patch("shield_data.data_upload_handler.Observer") as mock_observer_class,
        patch("shield_data.data_upload_handler.time.sleep") as mock_sleep,
    ):
        # Make sleep raise KeyboardInterrupt immediately to exit the loop
        mock_sleep.side_effect = KeyboardInterrupt

        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer

        try:
            upload_data_from_folder(str(results_dir))
        except KeyboardInterrupt:
            pass

        # Verify Observer was created and started
        mock_observer_class.assert_called_once()
        mock_observer.schedule.assert_called_once()
        mock_observer.start.assert_called_once()
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()


def test_upload_data_from_folder_handles_keyboard_interrupt(tmp_path: Path):
    """Test that upload_data_from_folder gracefully handles Ctrl+C.

    When KeyboardInterrupt is raised, the observer should be stopped
    and joined cleanly.
    """
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    with (
        patch("shield_data.data_upload_handler.Observer") as mock_observer_class,
        patch("shield_data.data_upload_handler.time.sleep") as mock_sleep,
    ):
        mock_sleep.side_effect = KeyboardInterrupt
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer

        # Should not raise, should handle gracefully
        upload_data_from_folder(str(results_dir), check_interval=10, batch_delay=3)

        # Verify cleanup happened
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()


def test_upload_data_from_folder_uses_custom_intervals(tmp_path: Path):
    """Test that upload_data_from_folder uses custom timing parameters.

    The function should respect custom check_interval and batch_delay
    parameters when setting up monitoring.
    """
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    with (
        patch("shield_data.data_upload_handler.Observer") as mock_observer_class,
        patch("shield_data.data_upload_handler.time.sleep") as mock_sleep,
        patch("shield_data.data_upload_handler.Handler") as mock_handler_class,
    ):
        mock_sleep.side_effect = KeyboardInterrupt
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer

        upload_data_from_folder(str(results_dir), check_interval=15, batch_delay=5)

        # Verify Handler was created with custom batch_delay
        mock_handler_class.assert_called_once_with(str(results_dir), 5)
        # Verify sleep was called with custom check_interval
        mock_sleep.assert_called_with(15)
