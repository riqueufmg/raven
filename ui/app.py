from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


from cli.commands.discover import (
    DiscoveryError,
    run_discovery,
)
from cli.config import ConfigError
from cli.repository import (
    RepositoryError,
    repository_name_from_url,
)
from ui.services.candidates_service import (
    UICandidatesError,
    load_candidate_targets,
    start_reproduction,
)
from ui.services.config_service import (
    UIConfigError,
    load_ui_config,
    save_discovery_config,
)
from ui.services.jobs_service import (
    UIJobsError,
    get_jobs,
    get_latest_job,
    read_job_log,
    status_category,
)
from ui.services.resources_service import (
    UIResourcesError,
    get_job_resources,
    get_machine_resources,
)
from ui.services.results_service import (
    SMELL_ORDER,
    STATUS_ORDER,
    UIResultsError,
    load_results_summary,
)


DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "config"
    / "raven.yml"
)


def format_timestamp(
    value: str | None,
) -> str:
    if not value:
        return "-"

    try:
        parsed = datetime.fromisoformat(
            value
        )

        return parsed.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    except ValueError:
        return value


def parse_analysis_date(
    value: str,
):
    try:
        return datetime.strptime(
            value,
            "%d-%m-%Y",
        ).date()

    except ValueError as exc:
        raise UIConfigError(
            "The configured analysis date "
            f"'{value}' is invalid. "
            "Expected format: DD-MM-YYYY."
        ) from exc


def ordered_values(
    values: set[str],
    preferred_order: list[str],
) -> list[str]:
    result = [
        value
        for value in preferred_order
        if value in values
    ]

    result.extend(
        sorted(
            value
            for value in values
            if value not in result
        )
    )

    return result


def render_phase(
    phase: str,
    category: str,
) -> None:
    if category == "success":
        st.success(
            phase
        )

    elif category == "error":
        st.error(
            phase
        )

    elif category == "running":
        st.info(
            phase
        )

    else:
        st.write(
            phase
        )


def render_discovery_summary(
    repository: str,
) -> None:
    job = get_latest_job(
        repository=repository,
        job_type="discovery",
    )

    st.subheader(
        "Current discovery status"
    )

    if job is None:
        st.info(
            "No discovery job has been "
            "recorded for this repository."
        )
        return

    col1, col2, col3 = (
        st.columns(3)
    )

    with col1:
        st.metric(
            "Status",
            job["phase"],
        )

    with col2:
        st.metric(
            "Repository",
            repository,
        )

    with col3:
        st.metric(
            "Job",
            job["id"][:20],
        )

    started = format_timestamp(
        job.get(
            "started_at"
        )
    )

    finished = format_timestamp(
        job.get(
            "finished_at"
        )
    )

    st.caption(
        f"Started: {started}"
    )

    if finished != "-":
        st.caption(
            f"Finished: {finished}"
        )

    log_value = (
        job.get("log")
        or ""
    )

    if log_value:
        st.caption(
            f"Log: {log_value}"
        )


def render_discovery_page() -> None:
    st.title(
        "RAVen Discovery"
    )

    st.write(
        "Configure a repository and start "
        "the complete discovery pipeline: "
        "historical mining, candidate analysis, "
        "and candidate validation."
    )

    config_path = DEFAULT_CONFIG

    try:
        loaded = load_ui_config(
            config_path
        )

    except UIConfigError as exc:
        st.error(
            f"Could not load configuration: "
            f"{exc}"
        )
        return

    config = loaded[
        "config"
    ]

    smell_registry = loaded[
        "smells"
    ]

    repository = config.get(
        "repository",
        {},
    )

    analysis = config.get(
        "analysis",
        {},
    )

    current_url = (
        repository.get(
            "url",
            "",
        )
    )

    current_branch = (
        repository.get(
            "branch",
            "main",
        )
    )

    current_since = str(
        analysis.get(
            "since",
            "",
        )
    )

    current_smells = (
        analysis.get(
            "smells",
            [],
        )
    )

    try:
        current_since_date = (
            parse_analysis_date(
                current_since
            )
        )

    except UIConfigError as exc:
        st.error(
            str(exc)
        )
        return

    st.subheader(
        "Configuration"
    )

    with st.form(
        "discovery_form"
    ):
        repository_url = (
            st.text_input(
                "Repository URL",
                value=current_url,
                placeholder=(
                    "https://github.com/"
                    "organization/project.git"
                ),
            )
        )

        branch = (
            st.text_input(
                "Branch",
                value=current_branch,
            )
        )

        since_date = (
            st.date_input(
                "Analyze commits since",
                value=current_since_date,
                format="DD-MM-YYYY",
                help=(
                    "Only commits on or after this "
                    "date will be considered during "
                    "historical mining."
                ),
            )
        )

        st.write(
            "Smells"
        )

        selected_smells = []

        columns = st.columns(
            min(
                4,
                max(
                    1,
                    len(
                        smell_registry
                    ),
                ),
            )
        )

        for index, (
            smell_id,
            definition,
        ) in enumerate(
            smell_registry.items()
        ):
            column = columns[
                index
                % len(columns)
            ]

            with column:
                checked = (
                    st.checkbox(
                        smell_id,
                        value=(
                            smell_id
                            in current_smells
                        ),
                        help=(
                            definition.get(
                                "display_name",
                                smell_id,
                            )
                        ),
                    )
                )

            if checked:
                selected_smells.append(
                    smell_id
                )

        st.divider()

        restart = (
            st.checkbox(
                "Restart discovery",
                value=False,
                help=(
                    "Force historical mining to run "
                    "again instead of reusing "
                    "compatible existing results."
                ),
            )
        )

        submitted = (
            st.form_submit_button(
                "Start discovery",
                type="primary",
                use_container_width=True,
            )
        )

    if submitted:
        if not selected_smells:
            st.error(
                "Select at least one smell "
                "before starting discovery."
            )

        else:
            formatted_since = (
                since_date.strftime(
                    "%d-%m-%Y"
                )
            )

            try:
                saved_path = (
                    save_discovery_config(
                        config_path=(
                            config_path
                        ),
                        repository_url=(
                            repository_url
                        ),
                        branch=branch,
                        since=formatted_since,
                        smells=(
                            selected_smells
                        ),
                    )
                )

                job = run_discovery(
                    config_path=(
                        saved_path
                    ),
                    restart=restart,
                )

            except (
                UIConfigError,
                ConfigError,
                RepositoryError,
                DiscoveryError,
            ) as exc:
                st.error(
                    str(exc)
                )

            else:
                st.success(
                    "Discovery job started."
                )

                st.write(
                    f"**Repository:** "
                    f"{job['repository']}"
                )

                st.write(
                    f"**Job:** "
                    f"{job['id']}"
                )

                st.write(
                    f"**Status:** "
                    f"{job['status']}"
                )

                st.write(
                    f"**Log:** "
                    f"`{job['log']}`"
                )

    if current_url:
        try:
            repo_name = (
                repository_name_from_url(
                    current_url
                )
            )

        except RepositoryError:
            return

        st.divider()

        render_discovery_summary(
            repo_name
        )


def render_machine_resources() -> None:
    try:
        resources = (
            get_machine_resources()
        )

    except UIResourcesError as exc:
        st.warning(
            str(exc)
        )
        return

    st.subheader(
        "Machine resources"
    )

    col1, col2, col3, col4 = (
        st.columns(4)
    )

    with col1:
        st.metric(
            "CPU usage",
            (
                f"{resources['cpu_percent']:.1f}%"
            ),
        )

    with col2:
        st.metric(
            "RAM used",
            (
                f"{resources['memory_used_gb']:.2f} GB"
            ),
        )

    with col3:
        st.metric(
            "RAM available",
            (
                f"{resources['memory_available_gb']:.2f} GB"
            ),
        )

    with col4:
        st.metric(
            "RAM total",
            (
                f"{resources['memory_total_gb']:.2f} GB"
            ),
        )

    st.caption(
        "CPU: "
        f"{resources['cpu_count_physical']} physical cores, "
        f"{resources['cpu_count_logical']} logical CPUs · "
        f"RAM usage: {resources['memory_percent']:.1f}%"
    )


@st.fragment(
    run_every="5s"
)
def render_live_job_resources(
    filtered_jobs: list[
        dict
    ],
) -> None:
    render_machine_resources()

    active_jobs = [
        job
        for job in filtered_jobs
        if status_category(
            job
        ) == "running"
    ]

    if not active_jobs:
        st.caption(
            "No active jobs are currently "
            "consuming monitored resources."
        )
        return

    try:
        resources = get_job_resources(
            active_jobs
        )

    except UIResourcesError as exc:
        st.warning(
            str(exc)
        )
        return

    rows = []

    for job in active_jobs:
        job_resources = resources.get(
            job["id"],
            {},
        )

        if job_resources.get(
            "available"
        ):
            cpu_value = (
                f"{job_resources['cpu_percent']:.1f}%"
            )

            ram_value = (
                f"{job_resources['memory_gb']:.2f} GB"
            )

            process_count = (
                job_resources[
                    "process_count"
                ]
            )

        else:
            cpu_value = "-"
            ram_value = "-"
            process_count = "-"

        rows.append(
            {
                "Repository":
                    job.get(
                        "repository"
                    )
                    or "-",
                "Task":
                    job.get(
                        "type"
                    )
                    or "-",
                "Target":
                    job.get(
                        "short_target"
                    )
                    or "-",
                "Status":
                    job.get(
                        "phase"
                    )
                    or "-",
                "CPU":
                    cpu_value,
                "RAM":
                    ram_value,
                "Processes":
                    process_count,
            }
        )

    st.subheader(
        "Active job resources"
    )

    st.dataframe(
        pd.DataFrame(
            rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "Resource usage includes the job process "
        "and its descendant processes. "
        "CPU usage may exceed 100% when a job "
        "uses multiple logical CPUs. "
        "Values refresh every 5 seconds."
    )


def render_jobs_page() -> None:
    st.title(
        "Background Jobs"
    )

    st.write(
        "Monitor discovery and reproduction "
        "jobs executed by RAVen."
    )

    try:
        jobs = get_jobs()

    except UIJobsError as exc:
        st.error(
            str(exc)
        )
        return

    if not jobs:
        render_machine_resources()

        st.info(
            "No RAVen jobs were found."
        )
        return

    repositories = sorted(
        {
            job.get(
                "repository"
            )
            for job in jobs
            if job.get(
                "repository"
            )
        }
    )

    task_types = sorted(
        {
            job.get(
                "type"
            )
            for job in jobs
            if job.get(
                "type"
            )
        }
    )

    filter_col1, filter_col2 = (
        st.columns(2)
    )

    with filter_col1:
        repository_filter = (
            st.selectbox(
                "Repository",
                [
                    "All repositories",
                    *repositories,
                ],
            )
        )

    with filter_col2:
        task_filter = (
            st.selectbox(
                "Task",
                [
                    "All tasks",
                    *task_types,
                ],
            )
        )

    filtered = []

    for job in jobs:
        if (
            repository_filter
            != "All repositories"
            and job.get(
                "repository"
            )
            != repository_filter
        ):
            continue

        if (
            task_filter
            != "All tasks"
            and job.get(
                "type"
            )
            != task_filter
        ):
            continue

        filtered.append(
            job
        )

    render_live_job_resources(
        filtered
    )

    st.divider()

    table_rows = []

    for job in filtered:
        table_rows.append(
            {
                "Repository":
                    job.get(
                        "repository"
                    )
                    or "-",
                "Task":
                    job.get(
                        "type"
                    )
                    or "-",
                "Target":
                    job.get(
                        "short_target"
                    )
                    or "-",
                "Status":
                    job.get(
                        "phase"
                    )
                    or "-",
                "Started":
                    format_timestamp(
                        job.get(
                            "started_at"
                        )
                    ),
                "Finished":
                    format_timestamp(
                        job.get(
                            "finished_at"
                        )
                    ),
            }
        )

    st.dataframe(
        pd.DataFrame(
            table_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader(
        "Job details"
    )

    options = {
        (
            f"{job.get('repository', '-')} | "
            f"{job.get('type', '-')} | "
            f"{job.get('short_target', '-')} | "
            f"{job.get('phase', '-')}"
        ): job
        for job in filtered
    }

    if not options:
        st.info(
            "No jobs match the selected filters."
        )
        return

    selected_label = (
        st.selectbox(
            "Select a job",
            list(
                options.keys()
            ),
        )
    )

    selected = options[
        selected_label
    ]

    detail_col1, detail_col2 = (
        st.columns(2)
    )

    with detail_col1:
        st.write(
            f"**Job ID:** "
            f"`{selected['id']}`"
        )

        st.write(
            f"**Repository:** "
            f"{selected.get('repository', '-')}"
        )

        st.write(
            f"**Task:** "
            f"{selected.get('type', '-')}"
        )

        st.write(
            f"**Target:** "
            f"{selected.get('target') or '-'}"
        )

    with detail_col2:
        st.write(
            "**Current phase:**"
        )

        render_phase(
            selected["phase"],
            status_category(
                selected
            ),
        )

        exit_code = (
            selected.get(
                "exit_code"
            )
        )

        st.write(
            f"**Exit code:** "
            f"{exit_code if exit_code is not None else '-'}"
        )

        st.write(
            f"**PID:** "
            f"{selected.get('pid') or '-'}"
        )

    st.write(
        f"**Started:** "
        f"{format_timestamp(selected.get('started_at'))}"
    )

    st.write(
        f"**Finished:** "
        f"{format_timestamp(selected.get('finished_at'))}"
    )

    st.write(
        f"**Log:** "
        f"`{selected.get('log') or '-'}`"
    )

    try:
        log_text = read_job_log(
            selected,
            max_lines=250,
        )

    except UIJobsError as exc:
        st.error(
            str(exc)
        )
        return

    st.subheader(
        "Recent log output"
    )

    if log_text:
        st.code(
            log_text,
            language="text",
        )

    else:
        st.info(
            "No log output is available "
            "for this job."
        )


def candidate_state_message(
    state: str,
) -> None:
    if state == "Reproduced":
        st.success(
            "Reproduced"
        )

    elif state == "Running":
        st.info(
            "Reproduction running"
        )

    elif state == "Existing":
        st.warning(
            "Existing environment"
        )

    else:
        st.write(
            "Not reproduced"
        )


def render_candidates_page() -> None:
    st.title(
        "Validated Candidates"
    )

    st.write(
        "Inspect validated smell-removal "
        "candidates across repositories and "
        "start historical environment reproduction."
    )

    try:
        catalog = load_candidate_targets(
            DEFAULT_CONFIG
        )

    except UICandidatesError as exc:
        st.error(
            str(exc)
        )
        return

    repositories = catalog[
        "repositories"
    ]

    if not repositories:
        st.info(
            "No candidate validation repositories "
            "were found."
        )
        return

    repository_selection = (
        st.selectbox(
            "Repository",
            [
                "All repositories",
                *repositories,
            ],
            key=(
                "candidate_repository_filter"
            ),
        )
    )

    selected_repository = (
        None
        if repository_selection
        == "All repositories"
        else repository_selection
    )

    try:
        data = load_candidate_targets(
            DEFAULT_CONFIG,
            repository=(
                selected_repository
            ),
        )

    except UICandidatesError as exc:
        st.error(
            str(exc)
        )
        return

    targets = data[
        "targets"
    ]

    summary_col1, summary_col2, summary_col3 = (
        st.columns(3)
    )

    with summary_col1:
        if selected_repository:
            st.metric(
                "Repository",
                selected_repository,
            )

        else:
            st.metric(
                "Repositories",
                data[
                    "repository_count"
                ],
            )

    with summary_col2:
        st.metric(
            "Valid candidates",
            data[
                "valid_candidate_count"
            ],
        )

    with summary_col3:
        st.metric(
            "Reproduction targets",
            data[
                "reproduction_target_count"
            ],
        )

    if not targets:
        st.info(
            "No validated reproduction targets "
            "were found for the selected repository."
        )
        return

    st.divider()

    state_options = [
        "All",
        *STATUS_ORDER,
    ]

    filter_col1, filter_col2 = (
        st.columns(2)
    )

    with filter_col1:
        state_filter = (
            st.selectbox(
                "Reproduction status",
                state_options,
            )
        )

    existing_smells = {
        smell
        for target in targets
        for smell in target[
            "smells"
        ]
    }

    all_smells = ordered_values(
        existing_smells,
        SMELL_ORDER,
    )

    with filter_col2:
        smell_filter = (
            st.selectbox(
                "Smell",
                [
                    "All",
                    *all_smells,
                ],
            )
        )

    filtered_targets = []

    for target in targets:
        if (
            state_filter
            != "All"
            and target["state"]
            != state_filter
        ):
            continue

        if (
            smell_filter
            != "All"
            and smell_filter
            not in target[
                "smells"
            ]
        ):
            continue

        filtered_targets.append(
            target
        )

    if not filtered_targets:
        st.info(
            "No reproduction targets match "
            "the selected filters."
        )
        return

    table_rows = []

    for target in filtered_targets:
        ordered_target_smells = (
            ordered_values(
                set(
                    target[
                        "smells"
                    ]
                ),
                SMELL_ORDER,
            )
        )

        row = {
            "Commit":
                target[
                    "short_commit"
                ],
            "Smells":
                ", ".join(
                    ordered_target_smells
                ),
            "Candidates":
                target[
                    "candidate_count"
                ],
            "Status":
                target[
                    "state"
                ],
        }

        if not selected_repository:
            row = {
                "Repository":
                    target[
                        "repository"
                    ],
                **row,
            }

        table_rows.append(
            row
        )

    st.dataframe(
        pd.DataFrame(
            table_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader(
        "Reproduction targets"
    )

    for target in filtered_targets:
        repository = target[
            "repository"
        ]

        commit = target[
            "commit"
        ]

        short_commit = target[
            "short_commit"
        ]

        state = target[
            "state"
        ]

        ordered_target_smells = (
            ordered_values(
                set(
                    target[
                        "smells"
                    ]
                ),
                SMELL_ORDER,
            )
        )

        title_parts = []

        if not selected_repository:
            title_parts.append(
                repository
            )

        title_parts.extend(
            [
                short_commit,
                ", ".join(
                    ordered_target_smells
                ),
            ]
        )

        title = " · ".join(
            title_parts
        )

        with st.expander(
            title,
            expanded=False,
        ):
            info_col, status_col = (
                st.columns(
                    [3, 1]
                )
            )

            with info_col:
                st.write(
                    f"**Repository:** "
                    f"{repository}"
                )

                st.write(
                    f"**Commit:** "
                    f"`{commit}`"
                )

                st.write(
                    f"**Validated candidates:** "
                    f"{target['candidate_count']}"
                )

            with status_col:
                st.write(
                    "**Status:**"
                )

                candidate_state_message(
                    state
                )

            st.write(
                "**Candidate instances**"
            )

            candidate_rows = []

            for candidate in target[
                "candidates"
            ]:
                candidate_rows.append(
                    {
                        "Smell":
                            candidate[
                                "SmellAlias"
                            ],
                        "Entity":
                            candidate[
                                "Entity"
                            ],
                    }
                )

            candidate_dataframe = (
                pd.DataFrame(
                    candidate_rows
                )
            )

            if not candidate_dataframe.empty:
                smell_rank = {
                    smell: index
                    for index, smell
                    in enumerate(
                        SMELL_ORDER
                    )
                }

                candidate_dataframe[
                    "_smell_order"
                ] = (
                    candidate_dataframe[
                        "Smell"
                    ]
                    .map(
                        smell_rank
                    )
                    .fillna(
                        len(
                            SMELL_ORDER
                        )
                    )
                )

                candidate_dataframe = (
                    candidate_dataframe
                    .sort_values(
                        [
                            "_smell_order",
                            "Smell",
                            "Entity",
                        ]
                    )
                    .drop(
                        columns=[
                            "_smell_order"
                        ]
                    )
                )

            st.dataframe(
                candidate_dataframe,
                use_container_width=True,
                hide_index=True,
            )

            if state == "Not reproduced":
                if st.button(
                    "Reproduce",
                    key=(
                        "reproduce_"
                        f"{repository}_"
                        f"{commit}"
                    ),
                    type="primary",
                ):
                    try:
                        job = (
                            start_reproduction(
                                config_path=(
                                    DEFAULT_CONFIG
                                ),
                                repository=(
                                    repository
                                ),
                                commit=commit,
                            )
                        )

                    except UICandidatesError as exc:
                        st.error(
                            str(exc)
                        )

                    else:
                        st.success(
                            "Reproduction job started."
                        )

                        st.write(
                            f"**Job:** "
                            f"`{job['id']}`"
                        )

                        st.write(
                            f"**Log:** "
                            f"`{job['log']}`"
                        )

                        st.rerun()

            elif state == "Running":
                st.info(
                    "A reproduction job is "
                    "currently active for this commit."
                )

            elif state == "Reproduced":
                st.success(
                    "This historical environment "
                    "has already passed the final "
                    "offline validation."
                )

            elif state == "Existing":
                st.warning(
                    "A non-empty reproduction "
                    "environment already exists for "
                    "this commit, but it is not "
                    "recognized as successfully reproduced."
                )


def render_results_page() -> None:
    st.title(
        "Results"
    )

    st.write(
        "Summarize validated smell-removal "
        "candidates and historical reproduction "
        "progress across repositories."
    )

    try:
        catalog = load_candidate_targets(
            DEFAULT_CONFIG
        )

    except UICandidatesError as exc:
        st.error(
            str(exc)
        )
        return

    repositories = catalog[
        "repositories"
    ]

    if not repositories:
        st.info(
            "No candidate validation repositories "
            "were found."
        )
        return

    repository_selection = (
        st.selectbox(
            "Repository",
            [
                "All repositories",
                *repositories,
            ],
            key=(
                "results_repository_filter"
            ),
        )
    )

    selected_repository = (
        None
        if repository_selection
        == "All repositories"
        else repository_selection
    )

    try:
        results = (
            load_results_summary(
                DEFAULT_CONFIG,
                repository=(
                    selected_repository
                ),
            )
        )

    except UIResultsError as exc:
        st.error(
            str(exc)
        )
        return

    if selected_repository:
        st.subheader(
            selected_repository
        )

    else:
        st.subheader(
            "All repositories"
        )

    (
        metric_col1,
        metric_col2,
        metric_col3,
        metric_col4,
    ) = st.columns(
        4
    )

    with metric_col1:
        st.metric(
            "Valid candidates",
            results[
                "valid_candidates"
            ],
        )

    with metric_col2:
        st.metric(
            "Reproduction targets",
            results[
                "reproduction_targets"
            ],
        )

    with metric_col3:
        st.metric(
            "Reproduced",
            results[
                "reproduced"
            ],
        )

    with metric_col4:
        st.metric(
            "Not reproduced",
            results[
                "not_reproduced"
            ],
        )

    if not selected_repository:
        st.caption(
            f"{results['repository_count']} "
            "repositories included."
        )

    if results["running"]:
        st.info(
            f"{results['running']} reproduction "
            "target(s) currently running."
        )

    if results["existing"]:
        st.warning(
            f"{results['existing']} reproduction "
            "target(s) have an existing environment "
            "that has not been recognized as reproduced."
        )

    targets = results[
        "reproduction_targets"
    ]

    if targets:
        completion = (
            results[
                "reproduced"
            ]
            / targets
        )

        st.write(
            "**Reproduction progress**"
        )

        st.progress(
            completion,
            text=(
                f"{results['reproduced']} of "
                f"{targets} reproduction targets "
                "successfully reproduced"
            ),
        )

    st.divider()

    chart_col1, chart_col2 = (
        st.columns(2)
    )

    with chart_col1:
        st.subheader(
            "Candidates by smell"
        )

        smell_counts = results[
            "smell_counts"
        ]

        if smell_counts:
            smell_df = (
                pd.DataFrame(
                    {
                        "Smell":
                            list(
                                smell_counts.keys()
                            ),
                        "Candidates":
                            list(
                                smell_counts.values()
                            ),
                    }
                )
                .set_index(
                    "Smell"
                )
            )

            st.bar_chart(
                smell_df,
                y="Candidates",
                use_container_width=True,
            )

        else:
            st.info(
                "No candidate data available."
            )

    with chart_col2:
        st.subheader(
            "Reproduction targets by status"
        )

        status_counts = results[
            "status_counts"
        ]

        if status_counts:
            status_df = (
                pd.DataFrame(
                    {
                        "Status":
                            list(
                                status_counts.keys()
                            ),
                        "Targets":
                            list(
                                status_counts.values()
                            ),
                    }
                )
                .set_index(
                    "Status"
                )
            )

            st.bar_chart(
                status_df,
                y="Targets",
                use_container_width=True,
            )

        else:
            st.info(
                "No reproduction status "
                "data available."
            )

    st.divider()

    st.subheader(
        "Reproduction targets"
    )

    table = pd.DataFrame(
        results[
            "table_rows"
        ]
    )

    if table.empty:
        st.info(
            "No reproduction targets "
            "are available."
        )
        return

    existing_smells = {
        smell.strip()
        for value in table[
            "Smells"
        ]
        for smell in value.split(
            ","
        )
        if smell.strip()
    }

    smell_values = ordered_values(
        existing_smells,
        SMELL_ORDER,
    )

    existing_statuses = set(
        table[
            "Status"
        ].unique()
    )

    status_values = ordered_values(
        existing_statuses,
        STATUS_ORDER,
    )

    filter_col1, filter_col2 = (
        st.columns(2)
    )

    with filter_col1:
        smell_filter = (
            st.selectbox(
                "Filter by smell",
                [
                    "All",
                    *smell_values,
                ],
                key=(
                    "results_smell_filter"
                ),
            )
        )

    with filter_col2:
        status_filter = (
            st.selectbox(
                "Filter by status",
                [
                    "All",
                    *status_values,
                ],
                key=(
                    "results_status_filter"
                ),
            )
        )

    filtered_table = (
        table.copy()
    )

    if smell_filter != "All":
        filtered_table = (
            filtered_table[
                filtered_table[
                    "Smells"
                ].apply(
                    lambda value: (
                        smell_filter
                        in [
                            smell.strip()
                            for smell
                            in value.split(
                                ","
                            )
                        ]
                    )
                )
            ]
        )

    if status_filter != "All":
        filtered_table = (
            filtered_table[
                filtered_table[
                    "Status"
                ]
                == status_filter
            ]
        )

    status_rank = {
        status: index
        for index, status
        in enumerate(
            STATUS_ORDER
        )
    }

    filtered_table[
        "_status_order"
    ] = (
        filtered_table[
            "Status"
        ]
        .map(
            status_rank
        )
        .fillna(
            len(
                STATUS_ORDER
            )
        )
    )

    filtered_table = (
        filtered_table
        .sort_values(
            [
                "_status_order",
                "Repository",
                "Commit",
            ]
        )
        .drop(
            columns=[
                "_status_order"
            ]
        )
    )

    visible_columns = []

    if not selected_repository:
        visible_columns.append(
            "Repository"
        )

    visible_columns.extend(
        [
            "Commit",
            "Smells",
            "Candidates",
            "Status",
        ]
    )

    st.dataframe(
        filtered_table[
            visible_columns
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        f"Showing {len(filtered_table)} "
        f"of {len(table)} reproduction targets."
    )


def main() -> None:
    st.set_page_config(
        page_title="RAVen",
        page_icon="🪶",
        layout="wide",
    )

    with st.sidebar:
        st.title(
            "RAVen"
        )

        st.caption(
            "Real-world Automated "
            "Validation of Refactorings"
        )

        page = st.radio(
            "Navigation",
            [
                "Discovery",
                "Jobs",
                "Candidates",
                "Results",
            ],
        )

    if page == "Discovery":
        render_discovery_page()

    elif page == "Jobs":
        render_jobs_page()

    elif page == "Candidates":
        render_candidates_page()

    elif page == "Results":
        render_results_page()


if __name__ == "__main__":
    main()