"""setup.py - setup to build C modules for cpmath

"""
__version__="$Revision$"

from distutils.core import setup,Extension
from Cython.Distutils import build_ext
from numpy import get_include
import os

def configuration():
    extensions = [Extension(name="_cpmorphology",
                            sources=["src/cpmorphology.c"],
                            include_dirs=['src']+[get_include()],
                            extra_compile_args=['-O3']),
                  Extension(name="_watershed",
                            sources=["_watershed.pyx", "heap.pxi"],
                            include_dirs=['src']+[get_include()],
                            extra_compile_args=['-O3'])]
    dict = { "name":"cpmath",
             "description":"algorithms for CellProfiler",
             "maintainer":"Lee Kamentsky",
             "maintainer_email":"leek@broad.mit.edu",
             "cmdclass": {'build_ext': build_ext},
             "ext_modules": extensions
            }
    return dict

if __name__ == '__main__':
    if '/' in __file__:
        os.chdir(os.path.dirname(__file__))
    setup(**configuration())
    
