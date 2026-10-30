# **RAVen**

<u>R</u>eal-world <u>A</u>utomated <u>V</u>alidation of R<u>e</u>factori<u>n</u>gs

RAVen is an experimental infrastructure for mining and validating real-world refactorings and reproducing the historical Java/Maven environments in which they occurred.

The repository supports an ongoing empirical study on automated refactoring of design and architecture smells.

## Study Status

This repository supports an ongoing empirical study.

The dataset, candidate set, scripts, experimental configuration, and results may change while the study is in progress.

A stable version of the repository will be archived when the final experimental dataset and results are established.

## Workflow

The current workflow is organized into two main macroactivities:

```text
Repository history
        ↓
Discovery
        ├── Historical smell mining
        ├── Candidate analysis
        └── Candidate validation
        ↓
Validated candidates
        ↓
Reproduction target selection
        ↓
Historical commit reproduction
        ├── Codex environment reconstruction
        └── Offline Maven validation
        ↓
Reproducible benchmark instance
```

The **discovery** stage identifies historical transitions in which a design or architecture smell disappears and validates whether those transitions represent candidate smell-removal refactorings.

The resulting validated commits form a checkpoint from which individual historical environments can be selected for reproduction.

The **reproduction** stage reconstructs the environment required to build and test the historical commit containing the smell. Reproduction is performed separately for each selected commit.

## Supported Smells

RAVen currently considers the following smells:

- **IM** — Insufficient Modularization;
- **HM** — Hub-like Modularization;
- **GC** — God Component;
- **UD** — Unstable Dependency.

IM and HM are class-level smells.

GC and UD are package-level smells.

Smell metadata is defined in:

```text
config/smells.yml
```

This registry contains information such as smell name, granularity, DesigniteJava category, and corresponding analysis artifact.

## Requirements

The complete RAVen pipeline may require:

- Python 3;
- Git;
- DesigniteJava;
- RefactoringMiner;
- Codex CLI;
- local Java and Maven toolchains prepared by RAVen.

Not every stage requires every dependency.

Historical smell mining uses Git, Python, and DesigniteJava.

Candidate validation additionally uses RefactoringMiner.

Historical commit reproduction uses Codex CLI and the preserved Java and Maven toolchains.

The Codex CLI must be installed, configured, and authenticated before running the reproduction pipeline.

# RAVen CLI

RAVen provides a unified command-line interface for the main workflow.

The available commands can be inspected with:

```bash
python -m cli.main --help
```

The current main commands are:

```text
mine
analyze
validate
discover
reproduce
status
```

The individual `mine`, `analyze`, and `validate` commands are useful for debugging and partial execution.

For normal operation, the recommended workflow is:

```text
discover
    ↓
validated candidates
    ↓
reproduce
```

## Configuration

The main configuration file is:

```text
config/raven.yml
```

A typical configuration is:

```yaml
repository:
  url: https://github.com/javaparser/javaparser.git
  branch: master

analysis:
  since: "01-01-2026"
  smells:
    - IM
    - HM
    - GC
    - UD

mining:
  overwrite: false

paths:
  repositories: mining/repositories
  mining_results: mining/results
  candidate_validation: candidate_validation
  benchmark: benchmark
  benchmark_results: benchmark/results
  designite: tools/DesigniteJava.jar
  refactoring_miner: tools/RefactoringMiner-3.0.7
  smell_registry: config/smells.yml
```

The command-line interface and the future graphical interface use this configuration to identify the repository, branch, historical analysis period, enabled smells, and artifact locations.

# Background Jobs

Long-running RAVen operations are executed as background jobs.

This allows discovery and reproduction operations to continue after the initiating terminal command returns.

Job metadata is stored under:

```text
jobs/
```

Job logs are stored under:

```text
logs/jobs/
```

Each job records information such as:

- repository;
- task type;
- target commit, when applicable;
- current execution status;
- process identifier;
- start time;
- finish time;
- exit code;
- log location.

Different repositories may be processed concurrently.

Historical reproduction currently uses one shared Git checkout for each repository. Therefore, RAVen prevents simultaneous reproduction jobs for the same repository.

## Inspect Job Status

Background jobs can be inspected with:

```bash
python -m cli.main status
```

Example:

```text
Repository  Task          Target        Status         Started
----------  ------------  ------------  -------------  -------------------
javaparser  reproduction  bbcf0cdcebb3  Running Codex  2026-10-30 22:44:18
javaparser  discovery     -             Analyzed       2026-10-30 22:16:02
```

Discovery jobs may be presented using states such as:

```text
Pending
Analyzing
Analyzed
Analysis failed
```

Reproduction jobs may expose more detailed phases:

```text
Pending
Preparing repository
Preparing environment
Running Codex
Offline validation
Reproduced
Validation failed
Failed
```

The underlying background job status remains separate from these user-facing execution phases.

# Prepare Reproduction Toolchains

Historical commit reproduction relies on preserved Java and Maven distributions stored under:

```text
benchmark/toolchains/
├── java/
└── maven/
```

These toolchains must be prepared before historical reproduction.

Run:

```bash
./prepare_toolchains.sh
```

`prepare_toolchains.sh` downloads and preserves the Java and Maven distributions made available to the reconstruction process.

The exact distributions provided by a RAVen release are defined by the corresponding version of `prepare_toolchains.sh`.

Downloaded toolchains are execution artifacts and are not versioned in Git.

## Shared and Commit-Specific Artifacts

RAVen separates shared build tools from artifacts reconstructed for individual historical commits.

Shared Java and Maven distributions are stored under:

```text
benchmark/toolchains/
```

A shared repository checkout is stored under:

```text
benchmark/repositories/<repository>/repository/
```

Each historical commit receives an isolated reproduction environment:

```text
benchmark/repositories/<repository>/commits/<short-commit>/
```

Java and Maven distributions are not duplicated inside every commit environment.

Instead, the generated reproduction scripts reference the preserved distributions under:

```text
benchmark/toolchains/
```

Maven dependencies and other reconstructed historical artifacts remain isolated for each commit.

## Historical Toolchain Selection

RAVen does not assume one Java or Maven version for every historical repository.

During environment reconstruction, Codex may investigate historical evidence such as:

- `pom.xml`;
- Maven Wrapper configuration;
- CI workflow files;
- compiler source and target levels;
- project documentation;
- repository history;
- plugin requirements;
- dependency requirements.

Based on this evidence, a historically appropriate Java and Maven distribution is selected from the preserved RAVen toolchains.

The selected distributions and relevant historical justification can be recorded in the generated reproduction artifacts.

# Build or Extend the Benchmark

## 1. Discover Valid Historical Refactorings

The complete candidate-discovery pipeline can be started with:

```bash
python -m cli.main discover \
  --config config/raven.yml
```

The command creates a background job and returns control to the terminal.

The background discovery job executes:

```text
historical mining
        ↓
candidate analysis
        ↓
candidate validation
```

Validated candidate artifacts are stored under:

```text
candidate_validation/<repository>/
```

## Restart Discovery

By default, discovery reuses compatible previously completed work whenever possible.

To explicitly restart discovery from the beginning:

```bash
python -m cli.main discover \
  --config config/raven.yml \
  --restart
```

`--restart` forces historical mining to run again and performs fresh candidate validation.

Because mining may require analysis of thousands of historical commits, this option should be used intentionally.

# Historical Mining

The mining pipeline analyzes repository history with DesigniteJava.

Mining artifacts are kept separate from historical reproduction artifacts.

Repository clones used for mining are stored under:

```text
mining/repositories/<repository>/
```

Historical DesigniteJava results are stored under:

```text
mining/results/<repository>/
```

## Run Mining Independently

Mining can be executed independently with:

```bash
python -m cli.main mine \
  --config config/raven.yml
```

This command is mainly useful for debugging and partial execution.

## Mining Manifest

Completed mining executions record their configuration in:

```text
mining/results/<repository>/mining_manifest.json
```

The manifest records information such as:

- repository URL;
- branch;
- starting date;
- DesigniteJava analysis mode;
- completion status;
- number of analyzed commits.

Existing mining artifacts are reused only when their manifest is compatible with the current configuration.

If historical mining results exist but no compatible manifest is available, RAVen refuses to silently reuse them.

This prevents analysis results generated for different repositories, branches, or historical periods from being treated as equivalent.

## Candidate Analysis

After historical DesigniteJava analysis, RAVen identifies candidate smell-removal transitions.

Candidate analysis can be executed independently with:

```bash
python -m cli.main analyze \
  --config config/raven.yml
```

The generated candidate files are stored under:

```text
mining/results/<repository>/candidates/
```

For the currently supported smells, the directory may contain:

```text
IM_candidates.csv
HM_candidates.csv
GC_candidates.csv
UD_candidates.csv
```

A candidate represents a direct parent-child historical transition in which the target entity exists and the selected smell appears to have been removed.

These mining results are candidate transitions only.

They do not by themselves establish that a refactoring caused the smell removal.

# Candidate Validation

Historical smell-removal candidates are validated before build reproduction.

Validation can be executed independently with:

```bash
python -m cli.main validate \
  --config config/raven.yml
```

Existing validation results can be reused with:

```bash
python -m cli.main validate \
  --config config/raven.yml \
  --resume
```

## Validation Input

Candidate transitions contain information such as:

- repository;
- smell;
- target entity;
- commit containing the smell (`C`);
- subsequent commit where the smell appears to have been removed (`C'`).

## Validation Criteria

A candidate is retained only when all of the following conditions hold:

1. `C'` is a direct child of `C`;
2. the target entity still exists in `C'`;
3. DesigniteJava detects the smell in `C`;
4. DesigniteJava does not detect the smell in `C'`;
5. RefactoringMiner identifies at least one refactoring involving the target entity in the transition.

Build reproducibility is evaluated separately after candidate validation.

## Validation Output

Validation artifacts are stored per repository:

```text
candidate_validation/<repository>/
├── candidates.csv
├── results.csv
├── commits.csv
├── designite/
├── refactorings/
└── pairs/
```

`candidates.csv` contains the consolidated candidate set for the configured repository and smells.

`results.csv` contains candidate-level validation results.

`commits.csv` contains the unique historical commits that passed candidate validation and are eligible for reproduction.

Several validated smell instances may correspond to the same historical commit.

For this reason, the number of valid candidates can be larger than the number of unique reproduction targets.

# Reproduce Historical Commits

After candidate validation, RAVen reconstructs selected historical environments one commit at a time.

## Interactive Reproduction

To inspect validated reproduction targets and select one interactively:

```bash
python -m cli.main reproduce \
  --config config/raven.yml
```

Example:

```text
Validated historical commits
==============================================================================

[1] 2a156ba2f477  Reproduced
    HM | com.example.ClassA

[2] 8e616cd8366d  Reproduced
    IM | com.example.ClassB
    UD | com.example.package

[3] bbcf0cdcebb3  Not reproduced
    IM | com.example.ClassC

Select a commit to reproduce [number or commit prefix]:
```

Candidates associated with the same historical commit are grouped together.

## Reproduce a Specific Commit

A validated historical commit can also be selected directly:

```bash
python -m cli.main reproduce \
  --config config/raven.yml \
  --commit <commit-sha>
```

A unique commit prefix is also accepted.

The CLI only accepts commits present in the validated candidate results.

## Background Reproduction

Reproduction is started as a background job.

The initiating command returns after the job is created.

Execution can be monitored using:

```bash
python -m cli.main status
```

The corresponding background job log is stored under:

```text
logs/jobs/
```

Detailed Codex execution traces are stored inside the commit-specific reproduction environment.

# Historical Environment Reconstruction

The low-level historical reconstruction implementation is provided by:

```text
repro.py
```

It can also be executed directly:

```bash
python repro.py \
  --repo https://github.com/example/project.git \
  --commit <commit-sha>
```

The RAVen CLI invokes this script automatically after verifying that the selected commit is an eligible reproduction target.

RAVen attempts to reconstruct the historical build environment without modifying tracked project files.

The historical commit is treated as the artifact to reproduce.

The objective is to reconstruct a compatible environment, not to repair the project.

## Repository Preparation

For each repository, RAVen maintains a shared Git checkout:

```text
benchmark/repositories/<repository>/repository/
```

Before changing commits, RAVen verifies that the shared checkout does not contain working-tree changes.

If the requested commit is not available locally, the repository is fetched from its configured origin.

The repository is then checked out in detached-HEAD mode at the historical commit.

Because this checkout is shared among commit environments belonging to the same repository, concurrent reproduction jobs for the same repository are currently prevented.

# Codex Environment Reconstruction

RAVen uses the Codex CLI to investigate and reconstruct historical build environments.

Codex receives:

- the shared historical repository;
- the target commit;
- RAVen reproduction instructions;
- the isolated commit environment;
- the preserved Java and Maven toolchains available to the benchmark.

During environment reconstruction, Codex may inspect:

- source files;
- `pom.xml` files;
- Maven configuration;
- Maven Wrapper files;
- CI configuration;
- repository history;
- Java requirements;
- Maven requirements;
- dependency metadata;
- previous project versions;
- historical dependency sources.

Codex may configure the external reproduction environment using:

- an appropriate preserved Java distribution;
- an appropriate preserved Maven distribution;
- Maven settings;
- Maven profiles;
- Maven properties;
- environment variables;
- isolated dependency repositories;
- reconstructed historical dependencies;
- preserved runtime libraries, when necessary.

Codex must not modify tracked project source files, tests, POM files, wrapper files, or CI files merely to make the historical build pass.

Before RAVen accepts the reconstructed environment, the historical repository is checked again to verify that tracked project files remain unchanged.

# Commit-Specific Reproduction Environment

A commit-specific reproduction environment is stored under:

```text
benchmark/repositories/<repository>/commits/<short-commit>/
```

A generated environment may contain:

```text
m2/               isolated Maven repository
settings.xml       commit-specific Maven settings
reproduce.sh       executable reproduction script
manifest.txt       reconstruction metadata and validation status
codex_trace.log    Codex execution trace
validation.log     authoritative final validation log
AGENTS.md           reconstruction instructions
dependency-src/    reconstructed historical dependency sources, when required
runtime/           preserved runtime artifacts, when required
home/              isolated home directory, when required
logs/              additional reconstruction logs, when required
```

Not every historical environment requires every optional artifact.

# Isolated Maven Repository

Each historical commit uses an isolated Maven repository:

```text
benchmark/repositories/<repository>/commits/<short-commit>/m2/
```

The generated `reproduce.sh` explicitly configures Maven to use this repository rather than the user's normal Maven cache.

This allows the dependencies required by the historical build to be preserved independently for each benchmark instance.

When a historical dependency is unavailable from currently accessible repositories, RAVen may reconstruct the genuine historical artifact from its producer repository and install it into this isolated Maven repository.

RAVen must not substitute the contents of one dependency version under the Maven coordinates of another version.

# Commit-Specific Maven Configuration

Reconstructed environments include:

```text
settings.xml
```

The generated reproduction script explicitly selects this file.

This prevents the build from depending on the user's default Maven settings.

Additional profiles, properties, environment variables, native runtime libraries, isolated home directories, or reconstructed historical dependencies may also be preserved when required by a historical project.

# Final Offline Validation

A reproduction is considered successful only when the reconstructed environment can execute the historical project's tests in offline mode.

The authoritative final validation is performed by RAVen **outside the Codex session**.

Before running this validation, RAVen removes ambient Java and Maven configuration inherited from the environment, including:

```text
JAVA_HOME
MAVEN_HOME
M2_HOME
MAVEN_OPTS
MAVEN_ARGS
JAVA_TOOL_OPTIONS
JDK_JAVA_OPTIONS
```

The generated `reproduce.sh` is therefore responsible for selecting the reconstructed Java, Maven, Maven settings, isolated repository, profiles, properties, and other required configuration.

Conceptually, final validation corresponds to:

```bash
mvn -o clean test
```

using the reconstructed historical environment.

The exact command can contain additional historically justified settings, profiles, properties, or environment variables when required by the target project.

The final validation output is stored in:

```text
validation.log
```

The final result is appended to:

```text
manifest.txt
```

Successful reproductions contain:

```text
offline reproduction result: PASS
```

Failed final validations contain:

```text
offline reproduction result: FAIL
```

Offline execution is used as RAVen's reproducibility criterion.

# Reproduction Manifest

`manifest.txt` records information about the reconstructed environment.

Depending on the historical project, this may include:

- target repository;
- target commit;
- build system;
- historical toolchain evidence;
- selected Java distribution;
- selected Maven distribution;
- Maven settings;
- Maven local repository;
- relevant profiles;
- Maven properties;
- environment variables;
- reconstructed dependencies;
- runtime requirements;
- final offline validation result.

The manifest provides human-readable provenance for the reconstructed environment.

# Reproduction Script

The generated:

```text
reproduce.sh
```

acts as an executable description of the reconstructed historical environment.

The script is expected to:

1. locate its own commit environment;
2. locate the shared target repository;
3. verify the expected historical commit;
4. inspect repository changes before switching commits;
5. refuse unsafe repository state changes;
6. select the preserved Java distribution;
7. select the preserved Maven distribution;
8. select the commit-specific Maven settings;
9. use only the commit-specific Maven repository;
10. configure any additional historically required environment;
11. execute the complete Maven test lifecycle;
12. use Maven offline mode;
13. return the Maven process exit code.

The script must not use destructive Git operations such as:

```text
git reset --hard
git clean
```

to force the repository into a buildable state.

# Advanced and Low-Level Usage

The unified CLI is the recommended interface for normal RAVen operation.

The underlying scripts remain available for debugging, experimentation, and large batch execution.

## Analyze One Repository Directly

Candidate transitions can be extracted directly with:

```bash
python -m mining.analyze_results \
  --repo mining/repositories/<repository> \
  --results-root mining/results \
  --branch refs/heads/<branch> \
  --smells IM HM GC UD
```

The generated files are stored under:

```text
mining/results/<repository>/candidates/
```

## Consolidate Candidates Directly

Candidate files can be consolidated directly with:

```bash
python mining/collect_smell_candidates.py \
  --results-root mining/results \
  --repositories <repository> \
  --smells IM HM GC UD \
  --output candidate_validation/<repository>/candidates.csv
```

## Validate Candidates Directly

Candidate datasets can also be processed using the lower-level validation scripts:

```bash
python validate_candidates.py
```

Individual candidate pairs can be analyzed with:

```bash
python validate_pair.py \
  --repo <repository-url> \
  --c <commit-with-smell> \
  --cprime <commit-without-smell> \
  --smell <IM|HM|GC|UD> \
  --fqn <target-entity>
```

These lower-level commands are useful for debugging and manual experimental inspection.

# Batch Mining

RAVen retains the experimental batch mining workflow.

Multiple repositories can be mined with:

```bash
./mining/run_search_batch.sh <repositories_num> <parallel_workers>
```

For example:

```bash
./mining/run_search_batch.sh 20 3
```

The arguments specify the maximum number of repositories selected for the batch and the number of parallel workers.

A batch can be previewed with:

```bash
./mining/run_search_batch.sh 20 3 --dry-run
```

The mining batch runner uses its own repository metadata and scheduling logic.

This batch mechanism is separate from the background-job model exposed by the unified RAVen CLI.

# Batch Reproduction

Multiple historical commits can also be processed using the experimental batch runner:

```bash
./run_batch.sh
```

The batch runner reads:

```text
commits.csv
```

with columns:

```text
repository,url,commit
```

Example:

```csv
repository,url,commit
byte-buddy,https://github.com/raphw/byte-buddy.git,ae380bb57643eae40a2ffa7553e6093e256050a7
dropwizard,https://github.com/dropwizard/dropwizard.git,9e256a...
spring-batch,https://github.com/spring-projects/spring-batch.git,667a92...
```

For each row, the batch runner invokes the historical reproduction pipeline for commit `C`.

Previously completed successful environments can be skipped rather than reconstructed again.

The batch runner remains useful for large experimental executions.

For normal interactive use, the recommended workflow is:

```text
raven discover
        ↓
validated commits
        ↓
raven reproduce
```

# Tools

External analysis tools used by the study are stored or expected under:

```text
tools/
```

The current pipeline uses:

- **DesigniteJava** for design and architecture smell detection;
- **RefactoringMiner** for detecting refactorings between commits.

For example:

```text
tools/
├── DesigniteJava.jar
└── RefactoringMiner-*/
```

Large third-party binaries may not be versioned in Git.

The versions used in the final study should be preserved in the corresponding experimental release.

# Execution Artifacts and Logs

RAVen produces several categories of execution artifacts.

## Background Job Metadata

```text
jobs/
```

## Background Job Logs

```text
logs/jobs/
```

## Historical Mining Results

```text
mining/results/
```

## Historical Mining Logs

```text
mining/log/
```

## Candidate Validation Artifacts

```text
candidate_validation/
```

## Historical Reproduction Environments

```text
benchmark/repositories/
```

## Shared Java and Maven Toolchains

```text
benchmark/toolchains/
```

Commit-specific Codex traces and final validation logs are stored inside the corresponding historical reproduction environment.

These artifacts can be used to inspect failures, monitor long-running processes, reproduce experimental decisions, and audit historical environment reconstruction.

# Repository Structure

A simplified view of the current repository is:

```text
RAVen/
├── cli/
│   ├── commands/
│   │   ├── analyze.py
│   │   ├── discover.py
│   │   ├── mine.py
│   │   ├── reproduce.py
│   │   ├── status.py
│   │   └── validate.py
│   ├── config.py
│   ├── discovery_runner.py
│   ├── job_runner.py
│   ├── jobs.py
│   ├── main.py
│   └── repository.py
│
├── config/
│   ├── raven.yml
│   └── smells.yml
│
├── mining/
│   ├── repositories.csv
│   ├── search_candidates.py
│   ├── analyze_results.py
│   ├── collect_smell_candidates.py
│   ├── run_search_batch.sh
│   ├── repositories/
│   ├── results/
│   └── log/
│
├── candidate_validation/
│   └── <repository>/
│       ├── candidates.csv
│       ├── results.csv
│       ├── commits.csv
│       ├── designite/
│       ├── refactorings/
│       └── pairs/
│
├── benchmark/
│   ├── repositories/
│   │   └── <repository>/
│   │       ├── repository/
│   │       └── commits/
│   │           └── <short-commit>/
│   │               ├── m2/
│   │               ├── AGENTS.md
│   │               ├── settings.xml
│   │               ├── manifest.txt
│   │               ├── reproduce.sh
│   │               ├── codex_trace.log
│   │               └── validation.log
│   ├── results/
│   └── toolchains/
│       ├── java/
│       └── maven/
│
├── jobs/
│
├── logs/
│   └── jobs/
│
├── tools/
│
├── AGENTS.md
├── CODEX_PROMPT.md
├── prepare_toolchains.sh
├── repro.py
├── run_batch.sh
├── collect_results.py
├── repositories.csv
├── validate_pair.py
└── validate_candidates.py
```

Some execution directories and generated artifacts may not be versioned in Git.

# Scope

RAVen currently targets historical Java projects built with Maven.

The mining and validation pipeline targets design and architecture smell-removal transitions in Java repository histories.

The current study focuses on:

- Insufficient Modularization;
- Hub-like Modularization;
- God Component;
- Unstable Dependency.

The configuration architecture allows additional smells to be registered when their analysis is supported by the underlying pipeline.

The reproduction pipeline focuses on reconstructing the historical environment required to execute a commit's complete Maven test lifecycle.

RAVen does not modify tracked project artifacts merely to obtain a successful build.

Target projects using unsupported build systems are outside the current reproduction scope.

# Reproducibility Principle

RAVen treats the historical commit as the artifact to reproduce.

The objective is not to repair or modernize the historical project.

Instead, RAVen reconstructs the external environment required for that historical version to build and execute its tests.

A successful benchmark instance should remain executable using:

- the selected preserved Java distribution;
- the selected preserved Maven distribution;
- the isolated Maven repository;
- the commit-specific Maven settings;
- any historically required profiles and properties;
- any historically required environment variables;
- any reconstructed historical dependencies;
- any required preserved runtime artifacts;

without requiring changes to the tracked contents of the historical commit.

The generated `reproduce.sh`, together with the commit-specific artifacts and `manifest.txt`, provides the executable description and provenance of the reconstructed historical environment.