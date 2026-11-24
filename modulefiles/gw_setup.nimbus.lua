help([[
Load environment to run GFS workflow setup scripts on Nimbus
]])

-- Versions and module paths are set in versions/run.nimbus.ver;
-- the defaults below allow loading this module before sourcing it
local intel_modulepath=os.getenv("intel_modulepath") or "/opt/intel/oneapi/modulefiles"
local stack_core_path=os.getenv("stack_core_path") or "/lfs/work/alexander_richert/stack/spack-stack/envs/nco-sci-oneapi-2026.1.0/modules_flat/Core"
prepend_path("MODULEPATH", intel_modulepath)
prepend_path("MODULEPATH", stack_core_path)

local stack_python_ver=os.getenv("stack_python_ver") or "3.11.15"
local py_pyyaml_ver=os.getenv("py_pyyaml_ver") or "6.0.3"
local py_jinja2_ver=os.getenv("py_jinja2_ver") or "3.1.6"
local py_numpy_ver=os.getenv("py_numpy_ver") or "1.26.4"
local cmake_ver=os.getenv("cmake_ver") or "3.31.11"

load(pathJoin("python", stack_python_ver))
load("python-venv")
load(pathJoin("py-pyyaml", py_pyyaml_ver))
load(pathJoin("py-jinja2", py_jinja2_ver))
load(pathJoin("py-numpy", py_numpy_ver))
load(pathJoin("cmake", cmake_ver))

-- TODO: rocoto is not yet installed on Nimbus; load unconditionally once available
if isAvail("rocoto") then
    load("rocoto")
end

whatis("Description: GFS run setup environment")
