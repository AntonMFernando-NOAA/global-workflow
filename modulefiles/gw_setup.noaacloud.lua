help([[
Load environment to run GFS workflow setup scripts on noaacloud (Nimbus)
]])

-- Point Lmod to BOTH Intel's modules and Alexander's Spack-stack modules
prepend_path("MODULEPATH", "/opt/intel/oneapi/modulefiles")
prepend_path("MODULEPATH", "/lfs/work/alexander_richert/stack/spack-stack/envs/nco-sci-oneapi-2026.1.0/modules_flat/Core")

-- Load Intel compiler prerequisites
load("tbb")
load("compiler-rt")
load("umf")

-- Load Python and Jinja2 dependencies in the correct order
load("python/3.11.15")
load("python-venv/1.0")
load("py-pyyaml/6.0.3")
load("py-markupsafe/3.0.2")
load("py-jinja2/3.1.6")

-- Load MPI and the rest of the scientific libraries
load("mpi/2021.18")
load("hdf5/1.14.5")
load("netcdf-c/4.9.2")
load("netcdf-fortran/4.6.1")
load("parallelio/2.6.2")
load("bacio/2.4.1")
load("sp/2.5.0")
load("ip/5.4.0")
load("w3emc/2.13.0")
load("g2/3.5.1")
load("g2tmpl/1.17.0")
load("esmf/8.8.0")
load("fms/2025.03-gfs-constants")
