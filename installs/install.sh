#!/usr/bin/env bash
set -euo pipefail

repo="Danelaton/scrambify"
api_url="https://api.github.com/repos/${repo}/releases/latest"
user_install_dir="${HOME}/.local/bin"
system_install_dir="/usr/local/bin"
binary_name="scrambify"

blue="$(printf '\033[34m')"
green="$(printf '\033[32m')"
yellow="$(printf '\033[33m')"
red="$(printf '\033[31m')"
bold="$(printf '\033[1m')"
reset="$(printf '\033[0m')"

phase() {
  printf "%s==>%s %s%s%s\n" "${blue}" "${reset}" "${bold}" "$1" "${reset}"
}

info() {
  printf "%s%s%s\n" "${green}" "$1" "${reset}"
}

warn() {
  printf "%s%s%s\n" "${yellow}" "$1" "${reset}"
}

fail() {
  printf "%s%s%s\n" "${red}" "$1" "${reset}" >&2
  exit 1
}

require_tool() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required tool: $1"
}

detect_os() {
  case "$(uname -s)" in
    Darwin) printf "darwin" ;;
    Linux) printf "linux" ;;
    *) fail "Unsupported operating system" ;;
  esac
}

detect_arch() {
  case "$(uname -m)" in
    x86_64|amd64) printf "amd64" ;;
    arm64|aarch64) printf "arm64" ;;
    *) fail "Unsupported architecture" ;;
  esac
}

latest_version() {
  curl -fsSL "${api_url}" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1
}

choose_install_dir() {
  if [ -d "${user_install_dir}" ] || mkdir -p "${user_install_dir}" 2>/dev/null; then
    printf "%s" "${user_install_dir}"
    return
  fi
  printf "%s" "${system_install_dir}"
}

install_binary() {
  local source_path="$1"
  local target_dir="$2"
  local target_path="${target_dir}/${binary_name}"

  if [ -w "${target_dir}" ]; then
    install "${source_path}" "${target_path}"
  elif command -v sudo >/dev/null 2>&1; then
    sudo install "${source_path}" "${target_path}"
  else
    fail "Cannot write to ${target_dir} and sudo is unavailable"
  fi
}

phase "Checking prerequisites"
require_tool curl
require_tool tar
require_tool sed
require_tool install
require_tool uname
require_tool mktemp

phase "Detecting platform"
os_name="$(detect_os)"
arch_name="$(detect_arch)"
version="$(latest_version)"
[ -n "${version}" ] || fail "Unable to determine the latest release"
asset_name="scrambify_${version}_${os_name}_${arch_name}.tar.gz"
download_url="https://github.com/${repo}/releases/download/${version}/${asset_name}"
install_dir="$(choose_install_dir)"
info "Latest release: ${version}"
info "Target asset: ${asset_name}"

phase "Preparing installation directory"
mkdir -p "${install_dir}"
temp_dir="$(mktemp -d)"
archive_path="${temp_dir}/${asset_name}"

cleanup() {
  rm -rf "${temp_dir}"
}
trap cleanup EXIT

phase "Downloading release archive"
curl -fsSL "${download_url}" -o "${archive_path}" || fail "Download failed for ${download_url}"

phase "Extracting archive"
tar -xzf "${archive_path}" -C "${temp_dir}"
[ -f "${temp_dir}/${binary_name}" ] || fail "Archive did not contain ${binary_name}"

phase "Installing binary"
install_binary "${temp_dir}/${binary_name}" "${install_dir}"

phase "Summary"
installed_path="${install_dir}/${binary_name}"
info "Installed ${binary_name} to ${installed_path}"
case ":${PATH}:" in
  *":${install_dir}:"*) info "${install_dir} is already on PATH" ;;
  *) warn "Add ${install_dir} to PATH to run ${binary_name} from any shell" ;;
esac
info "Run '${binary_name} --help' to verify the installation"