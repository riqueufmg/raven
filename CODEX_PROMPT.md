Follow the rules in:

    commits/{{SHORT_COMMIT}}/AGENTS.md

## Paths

Shared target repository:

    repository/

Target commit:

    {{FULL_COMMIT}}

Commit environment:

    commits/{{SHORT_COMMIT}}/

Isolated Maven repository:

    commits/{{SHORT_COMMIT}}/m2/

Shared Java toolchains:

    ../../toolchains/java/

Shared Maven toolchains:

    ../../toolchains/maven/

From `commits/{{SHORT_COMMIT}}/reproduce.sh`, the shared toolchain directories are:

    ../../../../toolchains/java/
    ../../../../toolchains/maven/

## Task

Prepare a historically justified, self-contained Maven environment for the target commit so that the complete target lifecycle can be reproduced with:

    mvn clean test

and finally with Maven offline mode.

The repository is already checked out at the target commit. Do not create another clone of the target repository and do not modify tracked files.

First confirm that the target project is Maven-based. If it is Gradle-based rather than Maven-based, create the manifest with status `UNSUPPORTED_BUILD_SYSTEM`, explain why, and stop without attempting conversion.

## Toolchain requirements

Determine the historically appropriate Java and Maven versions from evidence such as historical CI, Maven Wrapper, Maven Enforcer, POM configuration, and project documentation.

The final environment must not depend on Java or Maven installations outside this benchmark.

Before obtaining a toolchain, inspect the shared directories and reuse a suitable version if already present:

    ../../toolchains/java/
    ../../toolchains/maven/

If a required Java or Maven distribution is absent, place it under the corresponding shared toolchain directory.

The final `reproduce.sh` must explicitly select those preserved toolchains. It must not rely on the caller's `JAVA_HOME`, Maven from `PATH`, SDKMAN, `/usr/lib/jvm`, `/usr/bin/mvn`, `~/.m2/settings.xml`, or `~/.m2/toolchains.xml`.

If Maven Wrapper identifies the historical Maven version, preserve/reuse that Maven distribution under the shared Maven toolchain directory rather than depending on a user-level wrapper cache.

## Maven configuration and cache

Use only:

    commits/{{SHORT_COMMIT}}/m2/

as the Maven local repository for this commit.

Always create a commit-specific `settings.xml` inside the commit environment and pass it explicitly with Maven `-s`, even when it only contains minimal/default settings. Preserve any required `toolchains.xml` or other Maven configuration there as well and reference it explicitly from `reproduce.sh`.

Before finishing, run the complete online `mvn clean test` lifecycle using the isolated repository to populate all dependencies, plugins, plugin dependencies, parent POMs, and other artifacts needed later.

Then run the same complete lifecycle offline. Do not finish while offline Maven still reports unresolved artifacts.

## Historical dependencies

Never install the contents of one dependency version under another version's Maven coordinates.

If a declared historical dependency is missing or a mutable SNAPSHOT now resolves to incompatible contents, reconstruct a historically justified artifact from the producer repository/history when possible.

Store producer source under:

    commits/{{SHORT_COMMIT}}/dependency-src/

Install reconstructed artifacts into the same isolated Maven repository:

    commits/{{SHORT_COMMIT}}/m2/

A dependency producer may use Gradle or another build system even though the target project must be Maven-based. Preserve producer provenance and artifact hashes. Do not claim a reconstructed SNAPSHOT is the exact historical binary unless evidence proves that.

## Files to create

Create:

    commits/{{SHORT_COMMIT}}/manifest.txt
    commits/{{SHORT_COMMIT}}/reproduce.sh
    commits/{{SHORT_COMMIT}}/settings.xml

Store diagnostic/build logs under:

    commits/{{SHORT_COMMIT}}/logs/

The manifest must record at least:

- target repository and full commit;
- target build system;
- Java distribution/version and preserved path;
- Maven version and preserved path;
- exact online command;
- exact offline command;
- relevant profiles/properties/environment variables;
- Maven settings/toolchains files, if any;
- reconstructed historical dependencies and provenance, if any;
- runtime requirements;
- online result;
- offline result;
- confirmation that tracked target files were not modified.

## reproduce.sh requirements

The script must:

1. determine its own directory;
2. use `../../repository` as the target repository;
3. expect commit `{{FULL_COMMIT}}`;
4. inspect HEAD and working-tree changes;
5. if the repository is clean and at another commit, checkout the target commit;
6. if modified and at another commit, abort without changing anything;
7. if modified and already at the target commit, preserve the changes and build them;
8. never run `git reset --hard` or `git clean`;
9. explicitly select the preserved Java distribution from `../../../../toolchains/java/`;
10. explicitly select the preserved Maven distribution from `../../../../toolchains/maven/`;
11. not depend on ambient `JAVA_HOME`, SDKMAN, system Maven, or user Maven configuration;
12. use only `./m2/` as the Maven local repository;
13. pass the commit-specific `settings.xml` explicitly with Maven `-s`;
14. use any additional commit-specific Maven configuration explicitly;
15. run the complete Maven `clean test` lifecycle in offline mode;
16. return Maven's exit code.

The final authoritative validation is performed by `repro.py` outside the Codex sandbox.

If sandbox restrictions prevent sockets or similar runtime capabilities, document that restriction and prepare the environment for external validation.

Before finishing, confirm that tracked target files remain unchanged and that `manifest.txt` and executable `reproduce.sh` exist.

## Reproduction consistency

The final `reproduce.sh` must preserve all configuration required by the
historically justified successful build, including relevant Maven profiles,
properties, settings, toolchains, and environment variables.

Do not omit required configuration when producing the final offline command.