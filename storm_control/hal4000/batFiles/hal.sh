#!/usr/bin/env bash
#
# Launch HAL with a chosen setup configuration file.
#
# Written for Git Bash on Windows, also works on Linux.
#
# Usage:
#   hal.sh [options] CONFIG
#
#   CONFIG is either a path to a setup .xml file, or the name of one in
#   hal4000/xml (or in $HAL_CONFIG_DIR), with or without the '.xml'
#   extension, e.g. 'blackfly_trigger_ready_config'.
#
# Options:
#   -s, --settings FILE   Settings (parameters) .xml file to load as the
#                         default, passed to HAL as --xml.
#   -l, --list            List the available setup configurations and exit.
#   -c, --check           Check that the Python environment can import
#                         HAL's dependencies and exit.
#   -n, --dry-run         Print the command that would be run and exit.
#   -h, --help            Show this help and exit.
#
# Environment variables:
#   HAL_PYTHON      Python interpreter to use. Default is the virtual
#                   environment at ~/venvs/hal.
#   HAL_CONFIG_DIR  Extra directory to search for setup configurations,
#                   searched before hal4000/xml.
#
# Examples:
#   hal.sh --list
#   hal.sh none_config
#   hal.sh blackfly_trigger_ready_config
#   hal.sh -s ~/hal_settings/merfish.xml blackfly_trigger_ready_config
#   HAL_PYTHON=/c/Python310/python.exe hal.sh none_config
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HAL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
XML_DIR="${HAL_DIR}/xml"

usage() {
    sed -n '3,/^$/p' "${BASH_SOURCE[0]}" | sed -e 's/^# \{0,1\}//'
}

die() {
    echo "hal.sh: $*" >&2
    exit 1
}

# Find the Python interpreter.
find_python() {
    if [[ -n "${HAL_PYTHON:-}" ]]; then
        echo "${HAL_PYTHON}"
        return
    fi
    local venv="${HOME}/venvs/hal"
    if [[ -x "${venv}/Scripts/python.exe" ]]; then
        echo "${venv}/Scripts/python.exe"       # Windows
    elif [[ -x "${venv}/bin/python" ]]; then
        echo "${venv}/bin/python"               # Linux
    else
        die "no Python found at ${venv}; create it or set HAL_PYTHON"
    fi
}

# Resolve a configuration name or path to a file.
resolve_config() {
    local name="$1"
    if [[ -f "${name}" ]]; then
        echo "$(cd "$(dirname "${name}")" && pwd)/$(basename "${name}")"
        return
    fi
    local dir
    for dir in ${HAL_CONFIG_DIR:+"${HAL_CONFIG_DIR}"} "${XML_DIR}"; do
        if [[ -f "${dir}/${name}" ]]; then
            echo "${dir}/${name}"
            return
        elif [[ -f "${dir}/${name}.xml" ]]; then
            echo "${dir}/${name}.xml"
            return
        fi
    done
    die "configuration '${name}' not found (try --list)"
}

list_configs() {
    local dir
    for dir in ${HAL_CONFIG_DIR:+"${HAL_CONFIG_DIR}"} "${XML_DIR}"; do
        [[ -d "${dir}" ]] || continue
        echo "${dir}:"
        local f
        for f in "${dir}"/*.xml; do
            [[ -e "${f}" ]] || continue
            # Only setup configurations, i.e. files that define modules.
            if grep -q "<modules>" "${f}"; then
                echo "  $(basename "${f}" .xml)"
            fi
        done
    done
}

check_env() {
    local python="$1"
    echo "Python: ${python}"
    "${python}" - <<'EOF'
import importlib, sys
print("  version", sys.version.split()[0])
ok = True
for name in ["PyQt5.QtCore", "numpy", "scipy", "tifffile", "PIL", "serial",
             "storm_control", "PyDAQmx", "PySpin"]:
    try:
        m = importlib.import_module(name)
        v = getattr(m, "__version__", getattr(m, "PYQT_VERSION_STR", ""))
        print("  ok     ", name, v)
    except Exception as e:
        ok = False
        print("  MISSING", name, "-", type(e).__name__ + ":", e)
sys.exit(0 if ok else 1)
EOF
}

# The log directory is <directory>/logs, where <directory> is set in the
# configuration file. HAL fails at start up if it does not exist.
make_log_dir() {
    local config="$1"
    local data_dir
    data_dir="$(sed -n 's:.*<directory[^>]*>\(.*\)</directory>.*:\1:p' "${config}" | head -n 1)"
    [[ -n "${data_dir}" ]] || return 0
    data_dir="${data_dir//\\//}"

    # Don't create a Windows path (C:/...) as a relative directory on Linux.
    if [[ "${data_dir}" =~ ^[A-Za-z]: ]]; then
        case "$(uname -s)" in
            MINGW*|MSYS*|CYGWIN*) ;;
            *) return 0 ;;
        esac
    fi
    mkdir -p "${data_dir%/}/logs"
}

# Parse arguments.
settings=""
dry_run=0
config_name=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -s|--settings)
            [[ $# -ge 2 ]] || die "$1 needs a file"
            settings="$2"
            shift 2
            ;;
        -l|--list)
            list_configs
            exit 0
            ;;
        -c|--check)
            check_env "$(find_python)"
            exit $?
            ;;
        -n|--dry-run)
            dry_run=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            die "unknown option '$1' (try --help)"
            ;;
        *)
            [[ -z "${config_name}" ]] || die "only one configuration can be given"
            config_name="$1"
            shift
            ;;
    esac
done

[[ -n "${config_name}" ]] || { usage; exit 1; }

python="$(find_python)"
config="$(resolve_config "${config_name}")"

cmd=("${python}" hal4000.py "${config}")
if [[ -n "${settings}" ]]; then
    [[ -f "${settings}" ]] || die "settings file '${settings}' not found"
    cmd+=(--xml "$(cd "$(dirname "${settings}")" && pwd)/$(basename "${settings}")")
fi

if [[ ${dry_run} -eq 1 ]]; then
    echo "cd ${HAL_DIR}"
    echo "${cmd[*]}"
    exit 0
fi

make_log_dir "${config}"

# HAL loads splash.png etc. relative to its own directory.
cd "${HAL_DIR}"
echo "Starting HAL with ${config}"
exec "${cmd[@]}"
