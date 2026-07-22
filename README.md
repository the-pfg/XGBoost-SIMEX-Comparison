# XGBoost-SIMEX-Comparison
A QGIS processing script written in Python to compare land cover classification output by an XGBoost model to SIMEX.

## Installation and Environment Requirements

- Download the XGB-SIMEX-comparison-PyQGIS.py file along with the INPUTS and OUTPUTS file folders
- Create a new project in a Python IDE of your choice, and drop the files above into the project folder

#### Environment setup:
- Ensure that you have an installation of QGIS on your computer. This script was built using QGIS Long-term Release 3.44.11
- Point your project's Python environment to the Python interpreter present in your QGIS installation. This is typically located under
  C:/Program Files/QGIS 3.xx.xx/apps/Python312/python.exe, or a similar directory
- This may not be enough for your IDE to find all the necessary plugins included with the QGIS installation. To remedy this, add these two interpreter paths to your project's settings:
  - C:/Program Files/QGIS 3.xx.xx/apps/qgis-ltr/python
  - C:/Program Files/QGIS 3.xx.xx/apps/qgis-ltr/python/plugins

Running the XGB-SIMEX-comparison-PyQGIS.py file should now produce the desired results. If there are additional missing modules/plugins, they may be in other locations within your QGIS installation.

## Using the Script

- Define the list of years to analyze, which temporal handling mode to use, and input/output file names in the "CONFIG OPTIONS" section located at the top of the main block.
- Double check that the qgis_install path matches the working directory of your QGIS installation. The working directory can be found by opening the Python console in QGIS and entering: " print(QgsApplication.prefixPath()) "
- *Make sure to follow the stipulations detailed in the comments of the CONFIG OPTIONS block. Most critical are the QGIS path and INPUT file names.*

## Understanding the Outputs

#### XGB Raster
The XGB raster is a multi-band raster .tif file that contains the bands: 
1,2,3 - probabilities of burned, logged, and intact, respectively;
4 - the predicted class (hard classification). 0 = burned, 1 = logged, 2 = intact

#### SIMEX Raster
The SIMEX raster is a multi-bad raster .tif file that contains the bands:
1 - The year of logging within SIMEX. The "no logging" polygon is labelled as the year of analysis/"year0"
2 - The legality of the logging polygon. -1 = no logging area, 0 = legal, 1 = illegal

#### Agreement Raster
The agreement raster is a single-band raster that characterizes the agreement/disagreement for each valid pixel. The values are as follows:
1 - Both datasets agree there is logging
2 - Both datasets agree there is no logging / intact
3 - XGB classifies as intact within a SIMEX polygon
4 - XGB classifies as logged outside of a SIMEX polygon
5 - XGB classifies as burned withing a SIMEX polygon
6 - XGB classifies as burned outside of a SIMEX polygon

