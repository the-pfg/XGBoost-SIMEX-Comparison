# XGBoost-SIMEX-Comparison
A QGIS processing script written in Python to compare land cover classification output by an XGBoost model to SIMEX.

## Installation and Environment Requirements

- Download the XGB-SIMEX-comparison-PyQGIS.py file along with the INPUTS and OUTPUTS file folders
- Create a new project in a Python IDE of your choice, and drop the files above into the project folder

### Environment setup:
- Ensure that you have an installation of QGIS on your computer. This script was built using QGIS Long-term Release 3.44.11
- Point your project's Python environment to the Python interpreter present in your QGIS installation. This is typically located under
  C:/Program Files/QGIS 3.xx.xx/apps/Python312/python.exe, or a similar directory
- This may not be enough for your IDE to find all the necessary plugins included with the QGIS installation. To remedy this, add these two interpreter paths to your project's settings:
  C:/Program Files/QGIS 3.xx.xx/apps/qgis-ltr/python, C:/Program Files/QGIS 3.xx.xx/apps/qgis-ltr/python/plugins

Running the XGB-SIMEX-comparison-PyQGIS.py file should now produce the desired results. If there are additional missing modules/plugins, they may be in other locations within your QGIS installation.

## Using the Script

- Define the list of years to analyze, which temporal handling mode to use, and output file names in the "CONFIG OPTIONS" section located at the top of the main block.
- Double check that the qgis_install path matches the working directory of your QGIS installation. The working directory can be found by opening the Python console in QGIS and entering:
  " print(QgsApplication.prefixPath()) "

#### Formatting INPUT files:
- In order for the script to properly find the XGBoost and SIMEX shapefiles for the comparison, you must format the names of the shapefiles as:
  XGB: " YYYY_results.shp " where YYYY is the associated 4 digit year
  SIMEX: " simex_polys.shp "
  and finally, place them within the INPUTS folder.
