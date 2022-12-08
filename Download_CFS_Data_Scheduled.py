# %% Import Packages
import argparse
import boto3
import botocore
import datetime
import os
import schedule
import time
import xarray as xr


# %% Help message


parser = argparse.ArgumentParser(
    description='''
                                  A quick script to pull the most recent 7 day forecast from the NOAA CFS Model
                    This script runs without any additional input and simply requires you to run it in the command line
                                Once run, it will create directories for the CFS data and derived netcdf and csv files
                           If these directories already exist, the script will clean out what's there and update the data
    If you are running the timed version of this script, it will execute at 01:00 every wednesday and can be stopped for 6 days afterwards

    Required packages: boto3, botocore, datetime, schedule, time, xarray, netcdf4, scipy, dask

     ''',
    epilog="""Happy Modeling.""", 
    formatter_class = argparse.RawDescriptionHelpFormatter # format this properly
    )
args = parser.parse_args()

# %% Adjustables and prep

# name the bucket from AWS
cfs_bucket = 'noaa-cfs-pds'

# How much data do we want
days = 7  # number of days
cycles2get = days*4  # 4 forecast cycles/day


def download_files():
    # establish files for data and output

    try:
        os.mkdir('output')
        os.mkdir('output/csv')
        os.mkdir('output/netcdf')
        os.mkdir('data')
    except:
        print('no new path made')

    # Remove all data priorly stored in data directory
    dir = 'data/'
    for f in os.listdir(dir):
        os.remove(os.path.join(dir, f))

        # Remove all data priorly stored in data directory
    dir = 'output/netcdf/'
    for f in os.listdir(dir):
        os.remove(os.path.join(dir, f))
    
    # Remove all data priorly stored in data directory
    dir = 'output/csv'
    for f in os.listdir(dir):
        os.remove(os.path.join(dir, f))

    # %% Set up Boto3 client and bucket

    # set up unsigned configuration for boto
    client = boto3.client('s3', config=botocore.client.Config(
        signature_version=botocore.UNSIGNED))

    # set the date and time

    keys = []  # empty string for keys

    day = datetime.date.today() - datetime.timedelta(days=1)  # get yesterdays date
    time = datetime.time(0, 0)  # set to the 0th hour
    dt = datetime.datetime.combine(day, time)  # pass as combined datetime

    prefix = dt.strftime('cfs.%Y%m%d/00/6hrly_grib_01/')

    # %% Construct filenames

    cfs_filebase = 'flxf'
    sdate = dt
    ensnum = '01'  # CFS Ensemble number
    fdate = sdate

    flx_files = []

    for i in range(cycles2get):

        sdatestr = sdate.strftime('%Y%m%d%H')
        fdatestr = fdate.strftime('%Y%m%d%H')
        flx_file = cfs_filebase+fdatestr + '.' + ensnum + '.' + sdatestr+'.grb2'

        flx_files.append(flx_file)

        # Update the valid datetime by adding six hours from the valid time just used
        fdate = fdate + datetime.timedelta(hours=6)

    # %%Download all the files

    # download into data directory
    os.chdir('data/')
    for flx_file in flx_files:
        client.download_file(cfs_bucket, prefix+flx_file, flx_file)
    os.chdir('..')

    # open and concatonate all the cfgrib :( data
    ds_cfs = xr.open_mfdataset('data/flxf*.grb2',  # set directory
                               engine='cfgrib',  # use the cfgrib data
                               # filter by surface level fluxes
                               filter_by_keys={'typeOfLevel': 'surface'},
                               concat_dim='valid_time',  # concatonate along the valid time
                               combine='nested')  # combine in a nested format

    # Get desired variables out of data
    # precip rate
    da_cfs_prate = ds_cfs['prate']
    # Temperature
    da_cfs_t = ds_cfs['t']
    # Snow Depth
    da_cfs_sde = ds_cfs['sde']
    # water runoff
    da_cfs_watr = ds_cfs['watr']

    # %% Save the data

    # Save as NetCDF Files
    os.chdir('output/netcdf')
    da_cfs_prate.to_netcdf('cfs_prate_'+sdate.strftime('%Y%m%d')+'.nc')
    da_cfs_t.to_netcdf('cfs_t_'+sdate.strftime('%Y%m%d')+'.nc')
    da_cfs_sde.to_netcdf('cfs_sde_'+sdate.strftime('%Y%m%d')+'.nc')
    da_cfs_watr.to_netcdf('cfs_watr_'+sdate.strftime('%Y%m%d')+'.nc')
    os.chdir('..')
    os.chdir('..')

    # Save as CSV
    os.chdir('output/csv/')

    da_cfs_prate.to_series().to_csv('cfs_prate_'+sdate.strftime('%Y%m%d')+'.csv')
    da_cfs_t.to_series().to_csv('cfs_t_'+sdate.strftime('%Y%m%d')+'.csv')
    da_cfs_sde.to_series().to_csv('cfs_sde_'+sdate.strftime('%Y%m%d')+'.csv')
    da_cfs_watr.to_series().to_csv('cfs_watr_'+sdate.strftime('%Y%m%d')+'.csv')

    os.chdir('..')
    os.chdir('..')

    print('Job''s done :)')


# %% Schedule a run

schedule.every().wednesday.at("01:00").do(download_files, f'downloading files for {dt}')


while 1:
    schedule.run_pending()
    time.sleep(86400*6) # sleep for 6 days
