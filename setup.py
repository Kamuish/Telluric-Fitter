# from distutils.core import setup, Extension
from setuptools import setup, Extension
# from distutils.extension import Extension
import os
import subprocess
import sys

# from distutils.command.install import install
from setuptools.command.install import install
import numpy
from Cython.Distutils import build_ext
import requests

"""
def import_error_message(package):
    print("You need to install cython before running setup.py")
    print("Run 'pip install {}'".format(package))
    print("       or")
    print("'apt-get install {}' (if using a debian-based linux OS)".format(package))
    print("       or")
    print("'conda install {}' (if you use anaconda python)".format(package))


try:
    from Cython.Distutils import build_ext
except ImportError:
    import_error_message('cython')
    sys.exit()

try:
    import numpy
except ImportError:
    import_error_message('numpy')
    sys.exit()

try:
    import requests
except ImportError:
    import_error_message('requests')
    sys.exit()
"""

"""
Below are some default values, which the user may change
"""
# Starting wavelength (in nm) to use for the binary line list
#  TelluricFitter will not be able to generate lines with lower wavelengths!
wavestart = 300


#Ending wavelength (in nm) to use for the binary line list
#  TelluricFitter will not be able to generate lines with higher wavelengths!
waveend = 5000


#The number of running directories for LBLRTM. We need more
#  than one so that we can run multiple instances of 
#  TelluricFitter at once without overwriting input files
num_rundirs = 4

# Telluric modeling directory. This code will put all the data files in this directory.
# NOTE: If you change this, you MUST make an environment variable call TELLURICMODELING that points
#   to the new location!
TELLURICMODELING = '{}/.TelFit/'.format(os.environ['HOME'])

# URL where the data is stored
DATA_URL = 'http://www.as.utexas.edu/~kgulliks/media/data/aerlbl_v12.2_package.tar.gz'

if not TELLURICMODELING.endswith('/'):
    TELLURICMODELING += '/'


def ensure_dir(d):
    """
    Ensure a directory exists. Create it if not
    """
    if not os.path.exists(d):
        os.makedirs(d)


def download_file(url, outfilename):
    """
    Download file from url, and save to outfilename
    :param url:
    :param outfilename:
    :return:
    """
    r = requests.get(url, stream=True)
    with open(outfilename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
                f.flush()
    return


def GetCompilerString():
    """
    The following function determines what the operating system is,
      and which fortran compiler to use for compiling lnfl and lblrtm.
      It returns the string that the makefiles for lnfl and lblrtm
      need.

      NOTE: This should all work for linux or Mac OSX, but NOT Windows!!
    """
    #First, get the operating system
    p = sys.platform
    if "linux" in p:
        output = "linux"
    elif "darwin" in p:
        output = "osx"
    else:
        raise OSError("Unrecognized operating system: %s" % p)

    #Next, find the fortran compiler to use
    compilers = ["ifort",
                 "gfortran",
                 "g95"]
    comp_strs = ["INTEL",
                 "GNU",
                 "G95"]
    found = False
    for i in range(len(compilers)):
        compiler = compilers[i]
        try:
            subprocess.check_call([compiler, '--help'], stdout=open("/dev/null"))
            found = True
        except OSError:
            found = False
        if found:
            break
    if not found:
        raise OSError("Suitable compiler not found!")
    else:
        output = output + comp_strs[i] + "sgl"
    return output





def MakeTAPE3(directory):
    """
    The following will generate a TAPE3, which is needed for LBLRTM.
     The directory of the lnfl executable must be given.
    """
    # Delete any tape files that are already there
    for fname in ["TAPE1", "TAPE2", "TAPE5", "TAPE6", "TAPE10"]:
        if fname in os.listdir(directory):
            subprocess.check_call(["rm", "{0:s}{1:s}".format(directory, fname)])


    #Make the parameter file (TAPE5)
    wavenum_start = ("%.3f" % (1e7 / waveend)).rjust(10)
    wavenum_end = ("%.3f" % (1e7 / wavestart)).rjust(10)
    lines = ["$ TAPE5 file for LNFL, generated by setup.py\n", ]
    lines.append("%s%s\n" % (wavenum_start, wavenum_end))
    lines.append("1111111111111111111111111111111111111111")
    outfile = open(u"{0:s}TAPE5".format(directory), "w")
    outfile.writelines(lines)
    outfile.close()


    #Link the HITRAN line list to the current directory
    linfile = u"{0:s}/aer_v_3.2/line_file/aer_v_3.2".format(TELLURICMODELING)
    subprocess.check_call(["ln", "-s", linfile, u"{0:s}TAPE1".format(directory)])


    #Run LNFL to generate TAPE3
    lnfl_ex = [f for f in os.listdir(directory) if "lnfl" in f][0]
    print "\nUsing LNFL to generate a linelist for use by LBLRTM"
    print "  You may change the wavelength range at the top of "
    print "  the setup.py script. Saving run information in"
    print "        lnfl_run.log"
    print "  This may take a while...\n"
    subprocess.check_call([u"./{0:s}".format(lnfl_ex)], stdout=open("lnfl_run.log", "w"),
                          stderr=subprocess.STDOUT, cwd=directory)

    return





def MakeLBLRTM():
    """
    The following is called by build. It does the following things
    1) Gets the lblrtm files from server
    2) Unpacks all the lblrtm tar-files
    3) Builds the lblrtm and lnfl executables using their makefiles
        Note: the fortran compiler is determined above
    4) Generates a TAPE3 using LNFL, which LBLRTM needs as a static input
    5) Generates rundirs in the current directory, and populates them
        with the necessary files
    6) Outputs the bash commands that need to be run in order to setup
        the correct environment variables, and offers to append these
        to the user's ~/.bashrc
    """

    # Get the data files from directory
    ensure_dir(TELLURICMODELING)
    outfile = '{}aerlbl_package.tar.gz'.format(TELLURICMODELING)
    if not os.path.exists(outfile):
        print('Downloading data from {} and putting it in directory {}'.format(DATA_URL, TELLURICMODELING))
        download_file(DATA_URL, outfile)
        subprocess.check_call(['tar', '-xzf', outfile, '-C', TELLURICMODELING])

    #Unpack the tar files
    for fname in ['aer_v_3.2.tar.gz', 'aerlnfl_v2.6.tar.gz', 'aerlbl_v12.2.tar.gz']:
        if fname in os.listdir(TELLURICMODELING):
            print "Un-packing %s" % fname
            subprocess.check_call(["tar", "-xzf", '{}{}'.format(TELLURICMODELING, fname), '-C', TELLURICMODELING])
        else:
            print "\n\n*****    Error!   *****"
            print "     {0:s} not found in current directory!\n\n".format(fname)
            sys.exit()


    #Build the executables
    make_str = GetCompilerString()
    subprocess.check_call(["make", "-f", "make_lnfl", make_str], cwd="{}lnfl/build".format(TELLURICMODELING))
    subprocess.check_call(["make", "-f", "make_lblrtm", make_str], cwd="{}lblrtm/build".format(TELLURICMODELING))


    #Generate a TAPE3, if necessary.
    if "TAPE3" not in os.listdir("{}lnfl".format(TELLURICMODELING)):
        MakeTAPE3("{}lnfl/".format(TELLURICMODELING))


    #Make run directories with all of the relevant files/scripts/etc.
    # THIS MAY NOT WORK IF PIP DOESN'T HAVE DATA WHERE I THINK IT WILL BE!
    for i in range(1, num_rundirs + 1):
        directory = "{}rundir{}".format(TELLURICMODELING, i)
        print(u"Making {0:s}".format(directory))
        ensure_dir(directory)
        ensure_dir(u"{0:s}/OutputModels".format(directory))
        for fname in ["runlblrtm_v3.sh", "MIPAS_atmosphere_profile", "ParameterFile", "TAPE5"]:
            subprocess.check_call(["cp", "data/{0:s}".format(fname), u"{0:s}/".format(directory)])

        if "TAPE3" in os.listdir(directory):
            subprocess.check_call(["rm", "%s/TAPE3" % directory])
        subprocess.check_call(["ln", "-s", u"{0:s}/lnfl/TAPE3".format(TELLURICMODELING),
                               u"{0:s}/TAPE3".format(directory)])

        lblrtm_ex = [f for f in os.listdir("{}lblrtm".format(TELLURICMODELING)) if f.startswith("lblrtm")][0]
        if "lblrtm" in os.listdir(directory):
            subprocess.check_call(["rm", u"{0:s}/lblrtm".format(directory)])
        subprocess.check_call(["ln", "-s", "{0:s}/lblrtm/{1:s}".format(TELLURICMODELING, lblrtm_ex),
                               u"{0:s}/lblrtm".format(directory)])

        #Make sure the permissions are correct:
        subprocess.check_call(["chmod", "-R", "777", u"{0:s}/".format(directory)])


    #Finally, we need to set the environment variable TELLURICMODELING.
    """
    line = "export TELLURICMODELING=%s/\n" % os.getcwd()
    print "\nLBLRTM is all set up! The TelluricFitter code requires an environment variable to know where the lblrtm run directories are. You can set the appropriate environment variable with the following command:"
    print "\n\t%s" % line
    inp = raw_input(
        "\nWould you like us to run this command, and append it to your bash profile (~/.bashrc), so that the environment variable will be set every time you open a new terminal? Note: if you ran setup.py as super-user, you should choose no and do it yourself! [Y/n] ")
    if "y" in inp.lower() or inp.strip() == "":
        infile = open("%s/.bashrc" % (os.environ["HOME"]), "a+r")
        lines = infile.readlines()
        if line in lines:
            print "The appropriate environment variable is already set!"
        else:
            infile.write(line)
        infile.close()
        subprocess.check_call(line, shell=True)
    """

    return


"""
The following classes call MakeLBLRTM, and then do the normal
  installation stuff
"""
class CustomInstallCommand(install):
    def run(self):
        MakeLBLRTM()
        install.run(self)


class CustomBuildExtCommand(build_ext):
    def run(self):
        MakeLBLRTM()
        build_ext.run(self)


"""
  This only does the install. Useful if something went wrong
  but LBLRTM already installed
"""
class OnlyInstall(install):
    def run(self):
        install.run(self)


requires = ['matplotlib',
            'numpy>=1.6',
            'scipy>=0.13',
            'astropy>=0.2',
            'lockfile',
            'pysynphot>=0.7',
            'fortranformat',
            'cython',
            'requests']

setup(name='TelFit',
      version='1.3.7',
      author='Kevin Gullikson',
      author_email='kgulliks@astro.as.utexas.edu',
      url="http://www.as.utexas.edu/~kgulliks/projects.html",
      description='A package to fit the telluric absorption in astronomical spectra.',
      py_modules=['TelluricFitter',
                  'MakeModel',
                  'DataStructures',
                  'MakeTape5'],
      packages=['telfit'],
      ext_modules=[Extension("FittingUtilities", ["src/FittingUtilities.c"],
                             include_dirs=[numpy.get_include()],
                             extra_compile_args=["-O3", "-funroll-loops"]),
      ],
      cmdclass={'build_ext': CustomBuildExtCommand,
                'FittingUtilities': build_ext,
                'SkipLBL': OnlyInstall},
      data_files=[('', ['data/MIPAS_atmosphere_profile',
                        'data/ParameterFile',
                        'data/TAPE5',
                        'data/runlblrtm_v3.sh']), ],
      install_requires=requires,
      setup_requires=['cython', 'requests', 'numpy>=1.6'],
      package_dir={'': 'src'}
)


