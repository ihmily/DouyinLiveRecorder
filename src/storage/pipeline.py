# -*- coding: utf-8 -*-
"""
Pipeline orchestration module for recording post-processing.

Implements a DAG-based pipeline for composable processing stages:
Recording → Conversion → Upload

Author: DouyinLiveRecorder
Date: 2026-01-06
"""
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class StageStatus(str, Enum):
    """Status of a pipeline stage execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    """Result of a stage execution."""
    status: StageStatus
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class StageInput:
    """Input for a pipeline stage."""
    segment_id: int
    local_file_path: str
    file_format: str
    session_id: int
    anchor_name: str
    platform: str
    extra: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Stage(Protocol):
    """Protocol for pipeline stages."""

    @property
    def name(self) -> str:
        """Stage name for logging and tracking."""
        ...

    async def process(self, input_data: StageInput) -> StageResult:
        """
        Process the input and return result.

        Args:
            input_data: Stage input with segment information

        Returns:
            StageResult with status and output data
        """
        ...


class BaseStage(ABC):
    """Base class for pipeline stages with common functionality."""

    def __init__(self):
        self._logger = None

    @property
    def logger(self):
        """Lazy-load logger to avoid circular imports."""
        if self._logger is None:
            try:
                from ..logger import logger
                self._logger = logger
            except ImportError:
                import logging
                self._logger = logging.getLogger(self.name)
        return self._logger

    @property
    @abstractmethod
    def name(self) -> str:
        """Stage name."""
        pass

    @abstractmethod
    async def process(self, input_data: StageInput) -> StageResult:
        """Process stage logic."""
        pass


class Pipeline:
    """
    DAG-based pipeline executor for recording post-processing.

    Stages are executed in dependency order. If a stage fails,
    subsequent dependent stages are skipped.
    """

    def __init__(self):
        self.stages: Dict[str, Stage] = {}
        self.dependencies: Dict[str, List[str]] = {}
        self._logger = None

    @property
    def logger(self):
        """Lazy-load logger."""
        if self._logger is None:
            try:
                from .logger import logger
                self._logger = logger
            except ImportError:
                import logging
                self._logger = logging.getLogger("Pipeline")
        return self._logger

    def add_stage(
        self,
        stage: Stage,
        depends_on: Optional[List[str]] = None
    ) -> "Pipeline":
        """
        Add a stage to the pipeline.

        Args:
            stage: Stage instance implementing the Stage protocol
            depends_on: List of stage names this stage depends on

        Returns:
            Self for method chaining
        """
        self.stages[stage.name] = stage
        self.dependencies[stage.name] = depends_on or []
        return self

    def _topological_sort(self) -> List[str]:
        """Sort stages by dependency order."""
        visited = set()
        result = []

        def visit(name: str):
            if name in visited:
                return
            visited.add(name)
            for dep in self.dependencies.get(name, []):
                if dep in self.stages:
                    visit(dep)
            result.append(name)

        for name in self.stages:
            visit(name)

        return result

    async def execute(
        self,
        input_data: StageInput,
        stop_on_failure: bool = True
    ) -> Dict[str, StageResult]:
        """
        Execute all stages in dependency order.

        Args:
            input_data: Initial input for the pipeline
            stop_on_failure: If True, skip remaining stages on failure

        Returns:
            Dictionary mapping stage names to their results
        """
        results: Dict[str, StageResult] = {}
        execution_order = self._topological_sort()

        # Track accumulated output
        accumulated_output = dict(input_data.extra)

        for stage_name in execution_order:
            stage = self.stages[stage_name]

            # Check if dependencies succeeded
            deps_ok = all(
                results.get(dep, StageResult(StageStatus.PENDING)).status == StageStatus.COMPLETED
                for dep in self.dependencies[stage_name]
            )

            if not deps_ok and stop_on_failure:
                results[stage_name] = StageResult(
                    status=StageStatus.SKIPPED,
                    error="Dependencies not met"
                )
                self.logger.warning(f"Stage '{stage_name}' skipped: dependencies not met")
                continue

            # Execute stage
            try:
                self.logger.info(f"Starting stage: {stage_name}")

                # Pass accumulated output in extra
                stage_input = StageInput(
                    segment_id=input_data.segment_id,
                    local_file_path=input_data.local_file_path,
                    file_format=input_data.file_format,
                    session_id=input_data.session_id,
                    anchor_name=input_data.anchor_name,
                    platform=input_data.platform,
                    extra=accumulated_output.copy()
                )

                result = await stage.process(stage_input)
                results[stage_name] = result

                # Accumulate output for next stages
                if result.status == StageStatus.COMPLETED:
                    accumulated_output.update(result.output)
                    self.logger.info(f"Stage '{stage_name}' completed successfully")
                else:
                    self.logger.warning(f"Stage '{stage_name}' finished with status: {result.status}")

            except Exception as e:
                self.logger.error(f"Stage '{stage_name}' failed with exception: {e}")
                results[stage_name] = StageResult(
                    status=StageStatus.FAILED,
                    error=str(e)
                )

                if stop_on_failure:
                    # Mark remaining stages as skipped
                    remaining = execution_order[execution_order.index(stage_name) + 1:]
                    for remaining_name in remaining:
                        if remaining_name not in results:
                            results[remaining_name] = StageResult(
                                status=StageStatus.SKIPPED,
                                error="Previous stage failed"
                            )
                    break

        return results


def create_default_pipeline(
    delete_after_upload: bool = True,
    cleanup_callback=None
) -> Pipeline:
    """
    Create the default recording pipeline with conversion and upload stages.

    Args:
        delete_after_upload: Whether to delete local files after successful upload
        cleanup_callback: Callback to trigger storage cleanup after upload

    Returns:
        Configured Pipeline instance
    """
    from .stages.convert import ConvertStage
    from .stages.upload import UploadStage

    pipeline = Pipeline()
    pipeline.add_stage(ConvertStage())
    pipeline.add_stage(
        UploadStage(
            delete_after_upload=delete_after_upload,
            cleanup_callback=cleanup_callback
        ),
        depends_on=["convert"]
    )

    return pipeline
