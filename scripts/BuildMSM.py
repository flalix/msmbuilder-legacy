#!/usr/bin/python
# This file is part of MSMBuilder.
#
# Copyright 2011 Stanford University
#
# MSMBuilder is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import sys
import numpy
import scipy.io

import ArgLib

from Emsmbuilder import Serializer,MSMLib

def EstimateUnSym(Counts,Assignments):
    """Implements the following protocol:
    1.  Use Tarjan's algorithm to find maximal (strongly) ergodic subgraph.
    2.  Estimate a general (non-reversible) transition matrix.
    3.  Calculate populations from stationary eigenvector.
    """
    print "Doing no symmetrization. Warning: the resulting model may not satisfy detailed balance and could have complex eigenvalues."
    CountsAfterTrimming,Mapping=MSMLib.ErgodicTrim(Counts)
    ReversibleCounts=CountsAfterTrimming
    MSMLib.ApplyMappingToAssignments(Assignments,Mapping)
    TC = MSMLib.EstimateTransitionMatrix(ReversibleCounts)
    EigAns=MSMLib.GetEigenvectors(TC,5)
    Populations=EigAns[1][:,0]
    return(CountsAfterTrimming,ReversibleCounts,TC,Populations,Mapping)

def EstimateSym(Counts,Assignments):
    """Implements the following protocol:
    1.  Symmetrize counts via C' = C+C.transpose()
    2.  Use Tarjan's algorithm to find maximal (strongly) ergodic subgraph.
    3.  Estimate a reversible transition matrix.
    4.  Calculate populations from normalized row sums of count matrix.
    """
    Counts = 0.5*(Counts + Counts.transpose())
    ReversibleCounts,Mapping=MSMLib.ErgodicTrim(Counts)
    MSMLib.ApplyMappingToAssignments(Assignments,Mapping)
    TC = MSMLib.EstimateTransitionMatrix(ReversibleCounts)
    Populations=numpy.array(ReversibleCounts.sum(0)).flatten()
    Populations/=Populations.sum()
    CountsAfterTrimming=ReversibleCounts
    return(CountsAfterTrimming,ReversibleCounts,TC,Populations,Mapping)

def EstimateMLE(Counts,Assignments,Prior=0.):
    """Implements the following protocol:
    1.  Use Tarjan's algorithm to find maximal (strongly) ergodic subgraph.
    2.  Estimate (via MLE) a reversible transition (TC) and count matrix (ReversibleCounts).
    3.  Calculate populations from row sums of count matrix.
    """
    CountsAfterTrimming,Mapping=MSMLib.ErgodicTrim(Counts)
    MSMLib.ApplyMappingToAssignments(Assignments,Mapping)
    ReversibleCounts = MSMLib.IterativeDetailedBalance(CountsAfterTrimming,Prior=Prior)
    TC = MSMLib.EstimateTransitionMatrix(ReversibleCounts)
    Populations=numpy.array(ReversibleCounts.sum(0)).flatten()
    Populations/=Populations.sum()
    return(CountsAfterTrimming,ReversibleCounts,TC,Populations,Mapping)

def EstimateMLE_TNC(Counts,Assignments,Prior=0.):
    """Implements the following protocol:
    1.  Use Tarjan's algorithm to find maximal (strongly) ergodic subgraph.
    2.  Estimate (via MLE-TNC) a reversible transition (TC) and count matrix (ReversibleCounts).
    3.  Calculate populations from row sums of count matrix.
    """
    CountsAfterTrimming,Mapping=MSMLib.ErgodicTrim(Counts)
    MSMLib.ApplyMappingToAssignments(Assignments,Mapping)
    ReversibleCounts = MSMLib.EstimateReversibleCountMatrix(CountsAfterTrimming,Prior=Prior)
    TC = MSMLib.EstimateTransitionMatrix(ReversibleCounts)
    Populations=numpy.array(ReversibleCounts.sum(0)).flatten()
    Populations/=Populations.sum()
    return(CountsAfterTrimming,ReversibleCounts,TC,Populations,Mapping)

def run(LagTime, Assignments, Symmetrize='MLE', MinCounts=0, Prior=0.0,OutDir="./Data/"):

    OldAss   = Assignments

    FnTProb  =OutDir+"/tProb.mtx"
    FnTCounts=OutDir+"/tCounts.mtx"
    FnTUnSym =OutDir+"/tCounts.UnSym.mtx"
    FnMap    =OutDir+"/Mapping.dat"
    FnAss    =OutDir+"/Assignments.Fixed.h5"
    FnPops   =OutDir+"/Populations.dat"
    outputlist=[FnTProb,FnTCounts,FnTUnSym,FnMap,FnAss,FnPops]
    for output in outputlist:
        ArgLib.CheckPath(output)
  
    # Enforce Counts
    if MinCounts:
        print "Enforcing that each state has %d observed transitions" % MinCounts 
        MSMLib.EnforceCounts(Assignments,LagTime=LagTime,MinCounts=MinCounts)

    # Scan trajectory assignments and count transitions
    NumStates=max(Assignments.flatten())+1
    Counts=MSMLib.GetCountMatrixFromAssignments(Assignments, NumStates, LagTime=LagTime, Slide=True)

    # Check that the symmetrization method is one that we've implemented!

    if Symmetrize in ["None","none",None]:
        CountsAfterTrimming,ReversibleCounts,TC,Populations,Mapping=EstimateUnSym(Counts,Assignments)
    elif Symmetrize=="Transpose":
        CountsAfterTrimming,ReversibleCounts,TC,Populations,Mapping=EstimateSym(Counts,Assignments)
    elif Symmetrize=="MLE":
        CountsAfterTrimming,ReversibleCounts,TC,Populations,Mapping=EstimateMLE(Counts,Assignments,Prior=Prior)
    elif Symmetrize=="MLE-TNC":
        CountsAfterTrimming,ReversibleCounts,TC,Populations,Mapping=EstimateMLE_TNC(Counts,Assignments,Prior=Prior)
    else:
        print "ERROR: Could not understand symmetrization method:", Symmetrize
        sys.exit(1)
       
    # Print a statement showing how much data was discarded in trimming
    num_prev  = len(numpy.where( OldAss.flatten() != -1 )[0] )
    num_fixed = len(numpy.where( Assignments.flatten() != -1 )[0] )
    percent = (1.0 - float(num_fixed) / float(num_prev)) * 100.0
    print "WARNING: Ergodic trimming discarded: %f percent of your data" % percent 
 
    # Save all output
    numpy.savetxt(FnPops, Populations)
    numpy.savetxt(FnMap, Mapping,"%d")
    scipy.io.mmwrite(str(FnTProb), TC)
    scipy.io.mmwrite(str(FnTCounts), ReversibleCounts)
    scipy.io.mmwrite(str(FnTUnSym), CountsAfterTrimming)
    Serializer.SaveData(FnAss, Assignments)

    for output in outputlist:
        print "Wrote: %s"%output

    return

if __name__ == "__main__":
    print """\nEstimates the counts and transition matrices from an
Assignments.h5 file. Reversible models can be calculated either from naive
symmetrization or estimation of the most likely reversible matrices (MLE,
recommended). Also calculates the equilibrium populations for the model
produced. Outputs will be saved in the directory of your input Assignments.h5
file.
\nOutput: tCounts.mtx, tProb.mtx, Populations.dat,  Mapping.dat,
Assignments.Fixed.h5, tCounts.UnSym.mtx\n\n"""

    arglist=["assignments", "symmetrize", "mincounts", "lagtime", "prior", "outdir"]
    options=ArgLib.parse(arglist)
    print sys.argv
    
    LagTime = float(options.lagtime)
    Assignments=Serializer.LoadData(options.assignments)

    run(LagTime,Assignments, Symmetrize=options.symmetrize, MinCounts=int(options.mincounts), Prior=float(options.prior),OutDir=options.outdir)
