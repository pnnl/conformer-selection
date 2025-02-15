"""Calculate and save pairwise rmsd between all conformers. Save as pandas dataframe
.pkl files by cycle. 

np.nan has replaced where 0.0's would have been used for multiplication friendly 
Similarity Down-selection (SDS). np.nan is used for log-summing friendly SDS.

This script is written for direct use with ISiCLE output, but can be modified for
general application.
"""
import pybel
import openbabel
import pandas as pd
import numpy as np
from os.path import *
import glob
from multiprocessing import Pool
from functools import partial
import argparse

def find_invalid_confs(ID, ADD, save=False, tot_cyc=1000, tot_geom=50):
    """Finds .xyz files belonging to conformers who do not have matching .tsv files generated by MOBCAL.
    Args:
      ID (string): Molecule identifier
      ADD (string): Adduct
      save (bool): if true, saves array to .txt

    Returns:
      List of paths to conformation .xyz in ISiCLE directory tree that have missing CCS calculations.
    """

    conformers = []  
    cycles = ['%04d' % x for x in range(1, tot_cyc+1)]
    geoms = ['%02d' % x for x in range(1, tot_geom+1)]
    
    geomdir = abspath(f'output/dft/{ID}_{ADD}')
    tsvpath = abspath('output/mobility/mobcal/conformer_ccs')
    tsvs = glob.glob(join(tsvpath, '*.tsv')) #e.g. RWZYAGGXGHYGMB-UHFFFAOYSA-N_+De_0001_geom01.tsv
    tsvs.sort()

    t = join(tsvpath, f'{ID}_{ADD}_' + '{}_geom{}.tsv')
    for c in cycles:
        for g in geoms:
            if t.format(c, g) not in tsvs:
                conformers.append(join(geomdir,
                                       f'cycle_{c}_geom{g}',
                                       f'{ID}_{ADD}_{c}_geom{g}.xyz'
                                      )
                                 )            
    
    if save == True:
        with open('invalid_conf_paths.txt', 'w') as f:
            for item in conformers:
                f.write(item + '\n')

    return conformers

def rmsd(target, ref, invalid):
    if target in invalid:
        return np.nan #0.0
    else:
        a = next(pybel.readfile("xyz", ref))
        b = next(pybel.readfile("xyz", target))
        align = openbabel.OBAlign(False, True)
        align.SetRefMol(a.OBMol)
        align.SetTargetMol(b.OBMol)
        align.Align()
        return align.GetRMSD()

def pwrmsd_writer_multinode(current_cyc, writedir, invalid, ID, ADD, tot_cyc=1000, tot_geom=50):
    """Calculates pairwise rmsd of a population, calculating each pair only one time.
        Writes each tot_cyc*tot_geom pw rmsd-containing array to a cycle specific .pkl

    Args:
      current_cyc (int): present cycle number
      writedir (string): path to directory to write the pw rmsd .pkl
      invalid (array): array of paths to invalid conformer .xyz files (are missing valid CCS values in .tsv files)
      
        
    """
    geomdir = abspath(f'output/dft/{ID}_{ADD}')
    confstring = join(geomdir, 'cycle_{}_geom{}', f'{ID}_{ADD}_' + '{}_geom{}.xyz')
                                #cycle_0001_geom02/BXNJHAXVSOCGBA-UHFFFAOYSA-N_+H_0001_geom02.xyz
    cycles = [x for x in range(0,tot_cyc)]
    geometries = [x for x in range(0,tot_geom)]
    
    #Initializie dataframe
    current_df = pd.DataFrame(columns=range(tot_cyc*tot_geom)) 

    for current_geom in geometries:
        row = []           

        # Append NaN's to rmsd comparisons that are calculated in a previous cycle
        prev = current_cyc*50 + current_geom
        for i in range(prev):
            row.append(np.nan)

        # Append np.nan now that we're on the current cycle and geometry
        row.append(np.nan) #row.append(0)

        # Check current conformer exists (i.e. was successful through ISiCLE)
        cstr = '%04d' % (current_cyc + 1)
        gstr = '%02d' % (current_geom + 1)
        conf0 = confstring.format(cstr, gstr, cstr, gstr)

        #Fill with np.nan's if conformer doesn't exist
        if conf0 in invalid:
            zeros = [np.nan for x in range(prev + 1, tot_cyc*tot_geom)] #0
            row.extend(zeros)
            current_df.loc[current_geom] = row
            continue

        # Build conformer list that the current geometry will calc pwrmsd against
        conformers = []
        cstr = '%04d' % (current_cyc + 1)
        for g in range(current_geom + 1, tot_geom):
            gstr = '%02d' % (g + 1)
            conformers.append(confstring.format(cstr, gstr, cstr, gstr))
        for c in range(current_cyc + 1, tot_cyc):
            cstr = '%04d' % (c + 1)
            for g in range(tot_geom):
                gstr = '%02d' % (g + 1)                   
                conformers.append(confstring.format(cstr, gstr, cstr, gstr))

        # Calculate pw rmsd  
        rmsd_partial = partial(rmsd, ref=conf0, invalid=invalid)
        with Pool() as p:                
            pwrmsd = p.map(rmsd_partial, conformers)
        #    pwrmsd = p.map(rmsd, args=(conformers, invalid))
        row.extend(pwrmsd)
        # Add row to current cycle dataframe
        current_df.loc[current_geom] = row

    # Write the completed cycle dataframe to .pkl
    cstr = '%04d' % (current_cyc + 1) 
    current_df.to_pickle(join(writedir, f'{ID}_{ADD}_cycle{cstr}_pwrmsd.pkl'))
        
        
        
if __name__ == '__main__':
    from time import time
    start = time()
    parser = argparse.ArgumentParser()
    parser.add_argument('start', type=int, help='start at this cycle')
    parser.add_argument('stop', type=int, help='stop at this cycle (non-inclusive)')

    args = parser.parse_args()

    # The following are scripted to utilize output directly from ISiCLE
     # but obviously can be modified for whatever directory trees
    ID = # If using output from ISiCLE, `ID` will be the inchi key, e.g. 'QBUVFDKTZJNUPP-BBROENKCNA-N'
    ADD = # e.g. '+Na'
    tot_cyc = 1000
    tot_geom = 50
    geomdirpath = abspath(f'output/dft/{ID}_{ADD}')
    writedir = abspath('pwRMSD')
    invalid = find_invalid_confs(ID, ADD, save=True, tot_cyc=tot_cyc, tot_geom=tot_geom)
    
    for c in range(args.start, args.stop):
        # Check if cycle has already been written
        cstr = '%04d' % (c + 1)
        if isfile(join(writedir, f'{ID}_{ADD}_cycle{cstr}_pwrmsd.pkl')):
            continue
        else:
            pwrmsd_writer_multinode(c, writedir, invalid, ID, ADD, tot_cyc=tot_cyc, tot_geom=tot_geom)

    print((time()-start)/3600, 'hrs')
