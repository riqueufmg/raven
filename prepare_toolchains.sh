#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLCHAINS="$ROOT/benchmark/toolchains"
JAVA_DIR="$TOOLCHAINS/java"
MAVEN_DIR="$TOOLCHAINS/maven"
DOWNLOAD_DIR="$TOOLCHAINS/.downloads"

JAVA_VERSIONS=(8 11 17 21 23)
MAVEN_VERSIONS=(3.2.5 3.8.3 3.8.4 3.8.8 3.9.6)

mkdir -p "$JAVA_DIR" "$MAVEN_DIR" "$DOWNLOAD_DIR"

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "ERROR: required command not found: $1" >&2
        exit 1
    fi
}

for cmd in curl tar sha1sum sha256sum sha512sum python3; do
    require_cmd "$cmd"
done

case "$(uname -m)" in
    x86_64|amd64)
        ADOPTIUM_ARCH="x64"
        ;;
    aarch64|arm64)
        ADOPTIUM_ARCH="aarch64"
        ;;
    *)
        echo "ERROR: unsupported architecture: $(uname -m)" >&2
        echo "Supported: x86_64/amd64 and aarch64/arm64." >&2
        exit 1
        ;;
esac

OS="linux"

download_temurin() {
    local major="$1"
    local install_dir="$JAVA_DIR/temurin-$major"
    local metadata="$DOWNLOAD_DIR/temurin-$major.json"
    local archive="$DOWNLOAD_DIR/temurin-$major.tar.gz"
    local api_url
    local package_url
    local expected_sha256
    local actual_sha256
    local release_name

    if [[ -x "$install_dir/bin/java" ]]; then
        echo "[Java $major] already installed: $install_dir"
        return
    fi

    api_url="https://api.adoptium.net/v3/assets/feature_releases/${major}/ga?architecture=${ADOPTIUM_ARCH}&heap_size=normal&image_type=jdk&jvm_impl=hotspot&os=${OS}&page=0&page_size=1&project=jdk&sort_method=DEFAULT&sort_order=DESC&vendor=eclipse"

    echo
    echo "============================================================"
    echo "[Java $major] querying Adoptium metadata..."

    curl -fL --retry 3 --retry-delay 2 \
        -o "$metadata" \
        "$api_url"

    readarray -t meta_values < <(
        python3 - "$metadata" <<'PY'
import json
import sys

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

if not data:
    raise SystemExit("No release returned by Adoptium API")

release = data[0]

package = None
for binary in release.get("binaries", []):
    if (
        binary.get("image_type") == "jdk"
        and binary.get("os") == "linux"
    ):
        package = binary.get("package")
        if package:
            break

if not package:
    raise SystemExit("No matching JDK package found in Adoptium metadata")

link = package.get("link")
checksum = package.get("checksum")
release_name = release.get("release_name", "")

if not link or not checksum:
    raise SystemExit("Adoptium metadata does not contain link/checksum")

print(link)
print(checksum)
print(release_name)
PY
    )

    package_url="${meta_values[0]:-}"
    expected_sha256="${meta_values[1]:-}"
    release_name="${meta_values[2]:-unknown}"

    if [[ -z "$package_url" || -z "$expected_sha256" ]]; then
        echo "ERROR: failed to obtain package URL/checksum for Java $major" >&2
        exit 1
    fi

    echo "[Java $major] release: $release_name"
    echo "[Java $major] downloading package..."

    curl -fL --retry 3 --retry-delay 2 \
        -o "$archive" \
        "$package_url"

    actual_sha256="$(sha256sum "$archive" | awk '{print $1}')"

    echo "[Java $major] verifying SHA-256..."

    if [[ "$expected_sha256" != "$actual_sha256" ]]; then
        echo "ERROR: SHA-256 mismatch for Java $major" >&2
        echo "Expected: $expected_sha256" >&2
        echo "Actual:   $actual_sha256" >&2
        exit 1
    fi

    rm -rf "$install_dir"
    mkdir -p "$install_dir"

    tar -xzf "$archive" \
        -C "$install_dir" \
        --strip-components=1

    if [[ ! -x "$install_dir/bin/java" ]]; then
        echo "ERROR: Java $major extraction did not create bin/java" >&2
        exit 1
    fi

    echo "[Java $major] installed:"
    echo "  $install_dir"

    "$install_dir/bin/java" -version 2>&1 | head -n 3
}

download_maven() {
    local version="$1"
    local install_dir="$MAVEN_DIR/apache-maven-$version"
    local filename="apache-maven-${version}-bin.tar.gz"
    local archive="$DOWNLOAD_DIR/$filename"
    local base_url="https://archive.apache.org/dist/maven/maven-3/${version}/binaries"

    local checksum_file
    local checksum_type
    local expected
    local actual

    if [[ -x "$install_dir/bin/mvn" ]]; then
        echo "[Maven $version] already installed: $install_dir"
        return
    fi

    echo
    echo "============================================================"
    echo "[Maven $version] downloading..."

    curl -fL --retry 3 --retry-delay 2 \
        -o "$archive" \
        "$base_url/$filename"

    #
    # Newer Maven releases publish SHA-512.
    # Older releases, such as Maven 3.2.5, publish SHA-1 instead.
    #
    if curl -fsI "$base_url/$filename.sha512" >/dev/null 2>&1; then

        checksum_type="sha512"
        checksum_file="$DOWNLOAD_DIR/$filename.sha512"

        curl -fL --retry 3 --retry-delay 2 \
            -o "$checksum_file" \
            "$base_url/$filename.sha512"

        expected="$(tr -d '[:space:]' < "$checksum_file")"
        actual="$(sha512sum "$archive" | awk '{print $1}')"

    elif curl -fsI "$base_url/$filename.sha1" >/dev/null 2>&1; then

        checksum_type="sha1"
        checksum_file="$DOWNLOAD_DIR/$filename.sha1"

        curl -fL --retry 3 --retry-delay 2 \
            -o "$checksum_file" \
            "$base_url/$filename.sha1"

        expected="$(tr -d '[:space:]' < "$checksum_file")"
        actual="$(sha1sum "$archive" | awk '{print $1}')"

    else
        echo "ERROR: no supported checksum found for Maven $version" >&2
        exit 1
    fi

    echo "[Maven $version] verifying ${checksum_type^^}..."

    if [[ "$expected" != "$actual" ]]; then
        echo "ERROR: checksum mismatch for Maven $version" >&2
        echo "Expected: $expected" >&2
        echo "Actual:   $actual" >&2
        exit 1
    fi

    rm -rf "$install_dir"

    tar -xzf "$archive" \
        -C "$MAVEN_DIR"

    if [[ ! -x "$install_dir/bin/mvn" ]]; then
        echo "ERROR: Maven $version extraction did not create bin/mvn" >&2
        exit 1
    fi

    echo "[Maven $version] installed:"
    echo "  $install_dir"
}

echo "Preparing local benchmark toolchains"
echo "Root:         $TOOLCHAINS"
echo "Architecture: $ADOPTIUM_ARCH"
echo
echo "Java majors:   ${JAVA_VERSIONS[*]}"
echo "Maven versions:${MAVEN_VERSIONS[*]}"

for version in "${JAVA_VERSIONS[@]}"; do
    download_temurin "$version"
done

for version in "${MAVEN_VERSIONS[@]}"; do
    download_maven "$version"
done

echo
echo "============================================================"
echo "Toolchain preparation complete."
echo
echo "Java installations:"
for version in "${JAVA_VERSIONS[@]}"; do
    java_home="$JAVA_DIR/temurin-$version"
    printf "  Java %-2s -> %s\n" "$version" "$java_home"
    "$java_home/bin/java" -version 2>&1 | head -n 1 | sed 's/^/      /'
done

echo
echo "Maven installations:"
for version in "${MAVEN_VERSIONS[@]}"; do
    maven_home="$MAVEN_DIR/apache-maven-$version"
    printf "  Maven %-5s -> %s\n" "$version" "$maven_home"
done

echo
echo "Download cache:"
echo "  $DOWNLOAD_DIR"
echo
echo "The .downloads directory may be deleted after installation."
