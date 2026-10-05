# Historical Maven Reproduction

## Goal

For one historical Git commit, reproduce the complete Maven lifecycle:

    mvn clean test

without modifying tracked project files. The final validation must run offline.

## Scope

- The target project must be Maven-based. If it is Gradle-based, stop and report `UNSUPPORTED_BUILD_SYSTEM`.
- A dependency producer may use Gradle or another build system when needed to reconstruct a historical dependency.
- Reproduce the historical environment; do not fix or modernize the target project.

## Rules

You may inspect POMs, Maven Wrapper, Enforcer rules, CI files, Git history, and documentation; select historically justified Java/Maven versions and profiles; and reconstruct unavailable historical dependencies.

Do not modify tracked source, tests, POMs, wrappers, or CI files; change dependency/plugin declarations; disable target tests or modules merely to pass; substitute another artifact under false Maven coordinates; or commit changes.

The target commit must remain unchanged.

## Self-contained Environment

Final reproduction artifacts must use only:

- Java distributions under `benchmark/toolchains/java/`;
- Maven distributions under `benchmark/toolchains/maven/`;
- the commit-specific isolated Maven repository under `m2/`;
- commit-specific configuration/files preserved in the environment, including an explicit Maven `settings.xml`.

Do not make `reproduce.sh` depend on SDKMAN, `/usr/lib/jvm`, system Maven, `~/.m2/settings.xml`, `~/.m2/toolchains.xml`, or other user-specific toolchains/configuration.

Reuse an existing shared Java/Maven toolchain when appropriate before downloading another one.

## Historical Dependencies

For missing or mutable historical dependencies, preserve provenance. Do not replace an unavailable historical artifact with a newer artifact. When reconstruction is necessary, record coordinates, producer repository/commit, build command, and artifact SHA-256.

Producer tests may be skipped when they are not required to produce the dependency. Target-project tests must not be skipped.

## Success Criterion

A case is `PASS` only when the complete target build succeeds with Maven offline mode using the isolated `m2` repository and the preserved toolchains.

If success requires modifying the historical target project, stop and document the failure instead.
