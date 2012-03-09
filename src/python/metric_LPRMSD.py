"""
Modified version of RMSD distance metric that does the following:

1) Returns the RMSD, rotation matrices, and aligned conformations
2) Permutes selected atomic indices.
3) Perform the alignment again.

"""

from Emsmbuilder.metrics import AbstractDistanceMetric, RMSD
from Emsmbuilder import _lprmsd
from Emsmbuilder.Trajectory import Trajectory
# this is a forked version of the msmbuilder rmsdcalc
# with a new method that does the one_to_many efficiently inside the c code
# since python array slicing can be really slow. Big speedup using this
# for the drift calculation
import numpy as np
import itertools
from scipy import optimize
import copy

PT = {'H' : 1.0079, 'He' : 4.0026, 
      'Li' : 6.941, 'Be' : 9.0122, 'B' : 10.811, 'C' : 12.0107, 'N' : 14.0067, 'O' : 15.9994, 'F' : 18.9984, 'Ne' : 20.1797, 
      'Na' : 22.9897, 'Mg' : 24.305, 'Al' : 26.9815, 'Si' : 28.0855, 'P' : 30.9738, 'S' : 32.065, 'Cl' : 35.453, 'Ar' : 39.948, 
      'K' : 39.0983, 'Ca' : 40.078, 'Sc' : 44.9559, 'Ti' : 47.867, 'V' : 50.9415, 'Cr' : 51.9961, 'Mn' : 54.938, 'Fe' : 55.845, 
      'Co' : 58.9332, 'Ni' : 58.6934, 'Cu' : 63.546, 'Zn' : 65.39, 'Ga' : 69.723, 'Ge' : 72.64, 'As' : 74.9216, 'Se' : 78.96, 
      'Br' : 79.904, 'Kr' : 83.8, 'Rb' : 85.4678, 'Sr' : 87.62, 'Y' : 88.9059, 'Zr' : 91.224, 'Nb' : 92.9064, 'Mo' : 95.94, 
      'Tc' : 98, 'Ru' : 101.07, 'Rh' : 102.9055, 'Pd' : 106.42, 'Ag' : 107.8682, 'Cd' : 112.411, 'In' : 114.818, 'Sn' : 118.71, 
      'Sb' : 121.76, 'Te' : 127.6, 'I' : 126.9045, 'Xe' : 131.293, 'Cs' : 132.9055, 'Ba' : 137.327, 'La' : 138.9055, 
      'Ce' : 140.116, 'Pr' : 140.9077, 'Nd' : 144.24, 'Pm' : 145, 'Sm' : 150.36, 'Eu' : 151.964, 'Gd' : 157.25, 'Tb' : 158.9253, 
      'Dy' : 162.5, 'Ho' : 164.9303, 'Er' : 167.259, 'Tm' : 168.9342, 'Yb' : 173.04, 'Lu' : 174.967, 'Hf' : 178.49, 
      'Ta' : 180.9479, 'W' : 183.84, 'Re' : 186.207, 'Os' : 190.23, 'Ir' : 192.217, 'Pt' : 195.078, 'Au' : 196.9665, 
      'Hg' : 200.59, 'Tl' : 204.3833, 'Pb' : 207.2, 'Bi' : 208.9804, 'Po' : 209, 'At' : 210, 'Rn' : 222, 'Fr' : 223, 
      'Ra' : 226, 'Ac' : 227, 'Th' : 232.0381, 'Pa' : 231.0359, 'U' : 238.0289, 'Np' : 237, 'Pu' : 244, 'Am' : 243, 
      'Cm' : 247, 'Bk' : 247, 'Cf' : 251, 'Es' : 252, 'Fm' : 257, 'Md' : 258, 'No' : 259, 'Lr' : 262, 'Rf' : 261, 
      'Db' : 262, 'Sg' : 266, 'Bh' : 264, 'Hs' : 277, 'Mt' : 268
}

def ReadPermFile(fnm):
    LL = []
    L  = []
    fopen = open(fnm).readlines()
    for ln, line in enumerate(fopen):
        s = line.strip()
        if s != '--':
            L.append(int(s))
        if (ln != 0 and s == '--') or (ln == len(fopen) - 1):
            LL.append(np.array(L))
            L = []
        else: continue
    return LL

class LPTraj(Trajectory):
    def __init__(self,S,atomindices=None,permuteindices=None):
        super(LPTraj,self).__init__(S)
        aidx = list(atomindices) if atomindices != None else []
        pidx = list(itertools.chain(*permuteindices)) if permuteindices != None else []
        self.haveplus = permuteindices != None
        if atomindices == None and permuteindices == None:
            self.TD = RMSD.TheoData(S['XYZList'])
            self.TDx = self.TD
        elif permuteindices == None:
            self.TD = RMSD.TheoData(S['XYZList'][:,np.array(aidx)])
            self.TDx = self.TD
        elif atomindices == None:
            self.TD = RMSD.TheoData(S['XYZList'])
            self.TDx = self.TD
        else:
            self.TD = RMSD.TheoData(S['XYZList'][:,np.array(aidx)])
            self.TDx = RMSD.TheoData(S['XYZList'][:,np.array(aidx+pidx)])
        
    def __getitem__(self, key):
        if isinstance(key, int) or isinstance(key, slice) or isinstance(key,np.ndarray):
            if isinstance(key, int):
                key = [key]
            newtraj = copy.copy(self)
            newtraj['XYZList'] = self['XYZList'][key]
            newtraj.TD = self.TD[key]
            if self.haveplus:
                newtraj.TDx = self.TDx[key]
            return newtraj
        return super(Trajectory, self).__getitem__(key)

def EulerMatrix(T1,T2,T3):
    DMat = np.mat(np.zeros((3,3),dtype = float))
    DMat[0,0] = np.cos(T1)
    DMat[0,1] = np.sin(T1)
    DMat[1,0] = -np.sin(T1)
    DMat[1,1] = np.cos(T1)
    DMat[2,2] = 1
    CMat = np.mat(np.zeros((3,3),dtype = float))
    CMat[0,0] = 1
    CMat[1,1] = np.cos(T2)
    CMat[1,2] = np.sin(T2)
    CMat[2,1] = -np.sin(T2)
    CMat[2,2] = np.cos(T2)
    BMat = np.mat(np.zeros((3,3),dtype = float))
    BMat[0,0] = np.cos(T3)
    BMat[0,1] = np.sin(T3)
    BMat[1,0] = -np.sin(T3)
    BMat[1,1] = np.cos(T3)
    BMat[2,2] = 1
    EMat = BMat*CMat*DMat
    return np.mat(EMat)

def AlignToMoments(elem,xyz1,xyz2=None):
    """Pre-aligns molecules to 'moment of inertia'.
    If xyz2 is passed in, it will assume that xyz1 is already
    aligned to the moment of inertia, and it simply does 180-degree
    rotations to make sure nothing is inverted."""
    xyz = xyz1 if xyz2 == None else xyz2
    I = np.zeros((3,3))
    for i, xi in enumerate(xyz):
        I += PT[elem[i]]*(np.dot(xi,xi)*np.eye(3) - np.outer(xi,xi))
    A, B = np.linalg.eig(I)
    # Sort eigenvectors by eigenvalue
    BB   = B[:, np.argsort(A)]
    determ = np.linalg.det(BB)
    Thresh = 1e-3
    if np.abs(determ - 1.0) > Thresh:
        if np.abs(determ + 1.0) > Thresh:
            print "AHOOGA, determinant is % .3f" % determ
        BB[:,2] *= -1
    xyzr = np.array(np.mat(BB).T * np.mat(xyz).T).T.copy()
    if xyz2 != None:
        xyzrr = AlignToDensity(elem,xyz1,xyzr,binary=True)
        return xyzrr
    else:
        return xyzr

def ComputeOverlap(theta,elem,xyz1,xyz2):
    """ 
    Computes an 'overlap' between two molecules based on some
    fictitious density.  Good for fine-tuning alignment but gets stuck
    in local minima.
    """

    xyz2R = np.array(EulerMatrix(theta[0],theta[1],theta[2])*np.mat(xyz2.T)).T
    Obj = 0.0
    for i in set(elem):
        for j in np.where(elem==i)[0]:
            for k in np.where(elem==i)[0]:
                dx = xyz1[j] - xyz2R[k]
                dx2 = np.dot(dx,dx)
                Obj -= np.exp(-0.5*dx2)
    return Obj

def AlignToDensity(elem,xyz1,xyz2,binary=False):
    """ 
    Pre-aligns molecules to some density.
    I don't really like this, but I have to start with some alignment
    and a grid scan just plain sucks.
    
    This function can be called by AlignToMoments to get rid of inversion problems
    """

    t0 = np.array([0,0,0])
    if binary:
        t1 = optimize.brute(ComputeOverlap,((0,np.pi),(0,np.pi),(0,np.pi)),args=(elem,xyz1,xyz2),Ns=2,finish=optimize.fmin_bfgs)
    else:
        t1 = optimize.brute(ComputeOverlap,((0,2*np.pi),(0,2*np.pi),(0,2*np.pi)),args=(elem,xyz1,xyz2),Ns=6,finish=optimize.fmin_bfgs)
    xyz2R = (np.array(EulerMatrix(t1[0],t1[1],t1[2])*np.mat(xyz2.T)).T).copy()
    return xyz2R

class LPRMSD(AbstractDistanceMetric):
    
    def __init__(self, atomindices=None, permuteindices=None, altindices=None, moments=False, gridmesh=0):
        self.atomindices = atomindices
        self.altindices = altindices
        self.permuteindices = permuteindices
        self.grid     = None
        self.moments  = moments
        if gridmesh > 0:
            # Generate a list of Euler angles
            self.grid = list(itertools.product(*[list(np.arange(0,2*np.pi,2*np.pi/gridmesh)) for i in range(gridmesh)]))

    def _compute_one_to_all(self, pt1, pt2, index1, b_xyzout=False):
        #=========================================#
        #           Required information          #
        #=========================================#
        # Two prepared trajectories
        # A list of lists of permutable indices
        # A list of nonpermutable indices (aka the AtomIndices)
        # Boolean of whether to do the grid scan

        if not self.atomindices and not self.permuteindices:
            self.atomindices = np.arange( pt2['XYZList'].shape[1] )

        Usage = 0
        if self.atomindices != None:
            Usage += 1000
        if self.permuteindices != None:
            Usage += 100
            pi_flat = np.array(list(itertools.chain(*self.permuteindices)))
            pi_lens = np.array([len(i) for i in self.permuteindices])
        elif self.altindices != None:
            Usage += 10
            pi_flat = np.array(self.altindices)
            pi_lens = np.array([len(self.altindices)])
        else:
            pi_flat = np.array([])
            pi_lens = np.array([])
        if b_xyzout :
            Usage += 1
        
        XYZOut = pt2['XYZList'].transpose(0,2,1).copy()
        XYZRef = pt1['XYZList'].transpose(0,2,1)[index1].copy()
        RotOut = np.zeros(len(pt2)*9,dtype='float32')
        RMSDOut = _lprmsd.LPRMSD_Multipurpose(Usage, pt1.TD.NumAtoms, pt1.TD.NumAtomsWithPadding, pt1.TD.NumAtomsWithPadding, 
                                              pt2.TD.XYZData, pt1.TD.XYZData[index1], pt2.TD.G, pt1.TD.G[index1],
                                              pt1.TDx.NumAtoms, pt1.TDx.NumAtomsWithPadding, pt1.TDx.NumAtomsWithPadding, 
                                              pt2.TDx.XYZData, pt1.TDx.XYZData[index1], pt2.TDx.G, pt1.TDx.G[index1],
                                              pi_flat, pi_lens, RotOut, XYZOut, XYZRef) 

        #np.savetxt('RMSD1.txt',RMSDOut)

        if b_xyzout:
            return RMSDOut, XYZOut.transpose(0,2,1)
        else:
            return RMSDOut

    def one_to_all_aligned(self, prepared_traj1, prepared_traj2, index1):
        """
        Inputs: Two trajectories (Unlike RMSD, this takes in raw trajectory files)

        Calculate a vector of distances from the index1th frame of prepared_traj1
        to all the frames in prepared_traj2. This always uses OMP parallelization.
      
        If you really don't want OMP paralellization (why not?), then you can modify
        the C code yourself.
      
        Returns: a vector of distances of length len(indices2)"""

        return self._compute_one_to_all(prepared_traj1, prepared_traj2, index1, b_xyzout=True)

    def prepare_trajectory(self, trajectory):
        """ Copies the trajectory and optionally performs pre-alignment using moments of inertia. """

        T1 = LPTraj(trajectory,self.atomindices,self.permuteindices)
        if self.moments:
            xyz1  = trajectory['XYZList'][0]
            xyz1 -= xyz1.mean(0)
            xyz1  = AlignToMoments(trajectory['AtomNames'],xyz1)
            for index2, xyz2 in enumerate(trajectory['XYZList']):
                xyz2 -= xyz2.mean(0)
                xyz2 = AlignToMoments(trajectory['AtomNames'],xyz1,xyz2)
                T1['XYZList'][index2] = xyz2
    
        else:
            for index, xyz in enumerate(trajectory['XYZList']):
                xyz -= xyz.mean(0)
                T1['XYZList'][index] = xyz.copy()
                
        return T1

    def one_to_all(self, prepared_traj1, prepared_traj2, index1):
        """
        Inputs: Two trajectories (Unlike RMSD, this takes in raw trajectory files)

        Calculate a vector of distances from the index1th frame of prepared_traj1
        to all the frames in prepared_traj2. This always uses OMP parallelization.
      
        If you really don't want OMP paralellization (why not?), then you can modify
        the C code yourself.
      
        Returns: a vector of distances of length len(indices2)"""

        return self._compute_one_to_all(prepared_traj1, prepared_traj2, index1, b_xyzout=False)

