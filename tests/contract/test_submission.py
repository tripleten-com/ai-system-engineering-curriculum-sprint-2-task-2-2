"""Coldline.

===================

File:              tests/contract/test_submission.py
Component:         Contract tests — Test Submission
Purpose:           Tests for the public answer and path checks for this Task's submission.
Interacts With:    Published interfaces and repository boundaries
Sprint/Task:       Sprint 2 — Project 2
Concepts:          Compatibility, ownership, export safety
Tools:             Python 3.12, pytest
"""

from pathlib import Path

import pytest
import yaml

from tests.contract.submission_validation import (
    SubmissionError,
    _load_one_document,
    main,
    validate_changed_paths,
    validate_submission,
)

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "docs/contracts/submission.schema.json"


def valid_answers(choice: str = "context_assembly") -> dict[str, object]:
    """Return a complete answer sheet naming one supported choice."""
    return {"answers": {"selected_boundary": choice}}


def _task_root(tmp_path: Path, submission_text: str) -> Path:
    """Stage a minimal Task root the public verifier can validate."""
    (tmp_path / "docs/contracts").mkdir(parents=True)
    (tmp_path / "submission.yaml").write_text(submission_text, encoding="utf-8")
    (tmp_path / "submission-sample.yaml").write_text(
        (ROOT / "submission-sample.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "docs/contracts/submission.schema.json").write_text(
        SCHEMA.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


@pytest.mark.parametrize("choice", ["retrieval_orchestration", "context_assembly"])
def test_both_supported_choices_pass_public_validation(tmp_path: Path, choice: str) -> None:
    """Neither choice is privileged: both must satisfy the published contract."""
    root = _task_root(tmp_path, yaml.safe_dump(valid_answers(choice)))

    validate_submission(root / "submission.yaml", SCHEMA)


def test_blank_template_fails_with_field_address(tmp_path: Path) -> None:
    """An untouched answer sheet must identify the incomplete field."""
    root = _task_root(tmp_path, (ROOT / "submission.yaml").read_text(encoding="utf-8"))

    with pytest.raises(SubmissionError, match="answers.selected_boundary"):
        validate_submission(root / "submission.yaml", SCHEMA)


def test_unsupported_choice_is_rejected(tmp_path: Path) -> None:
    """A third responsibility is not on offer in this Task."""
    root = _task_root(tmp_path, yaml.safe_dump(valid_answers("broad_decomposition")))

    with pytest.raises(SubmissionError, match="selected_boundary"):
        validate_submission(root / "submission.yaml", SCHEMA)


def test_unexpected_answer_field_is_rejected(tmp_path: Path) -> None:
    """Fields outside the published direct-answer schema must fail validation."""
    answers = valid_answers()
    mapping = answers["answers"]
    assert isinstance(mapping, dict)
    mapping["boundary_rationale"] = "no free text is assessed in this Task"
    root = _task_root(tmp_path, yaml.safe_dump(answers))

    with pytest.raises(SubmissionError, match="Additional properties"):
        validate_submission(root / "submission.yaml", SCHEMA)


def test_exact_sample_copy_is_rejected(tmp_path: Path) -> None:
    """The published sample must not be accepted as a student submission."""
    root = _task_root(tmp_path, (ROOT / "submission-sample.yaml").read_text(encoding="utf-8"))

    with pytest.raises(SubmissionError, match="fictional sample"):
        validate_submission(
            root / "submission.yaml",
            SCHEMA,
            sample_path=root / "submission-sample.yaml",
        )


def test_student_editable_paths_and_prefixes_are_permitted() -> None:
    """The advisory path gate must accept this Task's implementation surface."""
    validate_changed_paths(["submission.yaml"])
    validate_changed_paths(["src/api/extensions/wiring.py"])
    validate_changed_paths(["src/api/extensions/retrieval_orchestration.py"])
    validate_changed_paths(["src/api/extensions/context_assembly.py"])
    validate_changed_paths(["tests/student/test_my_boundary.py"])

    with pytest.raises(SubmissionError, match="src/api/retrieval_workflow.py"):
        validate_changed_paths(["src/api/retrieval_workflow.py"])

    with pytest.raises(SubmissionError, match="src/domain/services.py"):
        validate_changed_paths(["src/domain/services.py"])

    with pytest.raises(SubmissionError, match="tests/contract"):
        validate_changed_paths(["tests/contract/test_service_boundary.py"])

    with pytest.raises(SubmissionError, match="tests/doubles"):
        validate_changed_paths(["tests/doubles/retrieval.py"])

    with pytest.raises(SubmissionError, match="src/adapters"):
        validate_changed_paths(["src/adapters/retriever/postgres_hybrid.py"])


def test_public_entrypoint_reports_an_incomplete_answer_sheet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catch a verifier entrypoint that skips the real submission contract."""
    root = _task_root(tmp_path, (ROOT / "submission.yaml").read_text(encoding="utf-8"))

    assert main(root, changed_paths=[]) == 1
    assert "answers.selected_boundary is incomplete" in capsys.readouterr().err


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "answers: {value: first, value: second}\n",
        "answers: &answer {value: fictional}\n",
        "answers: *missing\n",
        "answers: {<<: {value: fictional}}\n",
        "answers: {value: 2026-09-04}\n",
        "answers: {value: !custom fictional}\n",
        "answers: {1: fictional}\n",
    ],
    ids=[
        "duplicate-key",
        "anchor",
        "alias",
        "merge-key",
        "date",
        "custom-tag",
        "non-string-key",
    ],
)
def test_non_json_yaml_constructs_are_rejected(tmp_path: Path, unsafe_text: str) -> None:
    """Reject restricted syntax before schema validation can mask a parser defect."""
    submission = tmp_path / "submission.yaml"
    submission.write_text(unsafe_text, encoding="utf-8")

    with pytest.raises(SubmissionError, match="restricted YAML"):
        _load_one_document(submission)


def test_multiple_yaml_documents_are_rejected(tmp_path: Path) -> None:
    """A second document cannot supply or replace the answer mapping."""
    submission = tmp_path / "submission.yaml"
    submission.write_text("answers: {}\n---\nanswers: {}\n", encoding="utf-8")

    with pytest.raises(SubmissionError, match="exactly one YAML mapping"):
        _load_one_document(submission)
