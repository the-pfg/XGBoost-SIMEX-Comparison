
#INITIALIZATION

#importing all necessary libraries
from typing import Any, Optional

from qgis.core import (
    QgsFeatureSink,
    QgsProcessingParameterRasterDestination,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsCoordinateReferenceSystem,
    QgsProcessingUtils,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFileDestination,
)
from qgis import processing
import shutil
from osgeo import gdal
import numpy as np
import pandas as pd

class XGBandSIMEXcompare(QgsProcessingAlgorithm):
    
    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.
    XGB_INPUT = "xgb_INPUT"
    SIMEX_INPUT = "simex_INPUT"
    YEAR = "YEAR"
    OUTPUT1 = "OUTPUT1"
    OUTPUT2 = "OUTPUT2"
    OUTPUT3 = "OUTPUT3"

    def name(self) -> str:
        #the algorithm name, used to ID the algorithm
        return "xgb_simex_compare"

    def displayName(self) -> str:
        #the translated algorithm name presented to the user
        return "Compare XGB and SIMEX"

    def group(self) -> str:
        #name of the group the algorithm belongs to
        return "scripts"

    def groupId(self) -> str:
        #unique ID of the group the algorithm belongs to
        return "scripts"

    def shortHelpString(self) -> str:
        #description/help message displayed when using the tool
        return "Analyzes agreement between XGBoost classification and SIMEX logging polygons along with various other statistics"

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        #define the inputs and outputs of the algorithm

        #add the vector input features sources
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.XGB_INPUT,
                "XGBoost Classifcation Layer",
                [QgsProcessing.SourceType.TypeVectorAnyGeometry],
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.SIMEX_INPUT,
                "SIMEX 1 Polygons Layer",
                [QgsProcessing.SourceType.TypeVectorAnyGeometry],
            )
        )

        #add a feature sink to store processed features
        self.addParameter(
            QgsProcessingParameterRasterDestination(self.OUTPUT1, "XGB Raster")
        )
        
        self.addParameter(
            QgsProcessingParameterRasterDestination(self.OUTPUT2, "SIMEX Raster")
        )
        
        self.addParameter(
            QgsProcessingParameterRasterDestination(self.OUTPUT3, "Agreement Raster")
        )
        
        self.addParameter(
            QgsProcessingParameterNumber(
            self.YEAR, "Year to Analyze",
            type = QgsProcessingParameterNumber.Type.Integer,
            defaultValue = 2019,
            minValue = 2019
            )
        )
        
    #rasterization helper function
    def rasterize_field(self, layer, field, extent_string, pixel_size, context, feedback, name):
        file_path = QgsProcessingUtils.generateTempFilename(f"{name}_{field}.tif")
        result_id = processing.run(
        "gdal:rasterize",
        {
            "INPUT": layer,
            "FIELD": field,
            "UNITS": 1,
            "WIDTH": pixel_size,
            "HEIGHT": pixel_size,
            "EXTENT": extent_string,
            "NODATA": -999,
            "INIT": -999,
            "DATA_TYPE": 6,
            "OUTPUT": file_path,
        },
        context = context, feedback = feedback, is_child_algorithm = True,
        )["OUTPUT"]
        raster = QgsProcessingUtils.mapLayerFromString(result_id, context)
        
        if raster is None:
            raise QgsProcessingException(f"Failed to rasterize {name}, {field}")
        return raster
        
    #raster stacking helper function
    def stack_bands(self, raster_layers, context, feedback, name):
        file_path = QgsProcessingUtils.generateTempFilename(f"{name}_stacked.tif")
        result_id = processing.run(
            "gdal:merge",
            {
                "INPUT": raster_layers,
                "NODATA_INPUT": -999,
                "NODATA_OUTPUT": -999,
                "DATA_TYPE": 6,
                "SEPARATE": True,
                "OUTPUT": file_path,
            },
            context = context, feedback = feedback, is_child_algorithm = True,
        )["OUTPUT"]
        stacked = QgsProcessingUtils.mapLayerFromString(result_id, context)
        if stacked is None:
            raise QgsProcessingException(f"Failed to stack bands for {name}")
        return stacked
    
#BEGIN PROCESSING BLOCK
    def processAlgorithm(self, parameters: dict[str, Any], context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:
        
        #retrieve the feature sources and sinks; 'dest_id' uniquely IDs the feature sink and must
        #be in the dictionary returned by the processAlgorithm function
        xgb_source = self.parameterAsSource(parameters, self.XGB_INPUT, context)
        simex_source = self.parameterAsSource(parameters, self.SIMEX_INPUT, context)
        
        #throw invalidSourceError if no source is detected
        if xgb_source is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.XGB_INPUT)
            )
        elif simex_source is None:
            raise QgsProcessingException(
                self.invalidSourceError(parameters, self.SIMEX_INPUT)
            )
        
#-------BEGIN MAIN PROCESSING ALGORITHM-----------------------------------------
        
        #fix geometries of source layers
        xgb_fixed = processing.run(
            "native:fixgeometries",
            {"INPUT": parameters[self.XGB_INPUT], "METHOD":1, "OUTPUT":"memory:"},
            context = context,
            feedback = feedback,
            is_child_algorithm = True,
            )["OUTPUT"]
        xgb_fixed_layer = QgsProcessingUtils.mapLayerFromString(xgb_fixed, context)
        
        simex_fixed = processing.run(
            "native:fixgeometries",
            {"INPUT": parameters[self.SIMEX_INPUT], "METHOD":1, "OUTPUT":"memory:"},
            context = context,
            feedback = feedback,
            is_child_algorithm = True,
            )["OUTPUT"]
        simex_layer = QgsProcessingUtils.mapLayerFromString(simex_fixed, context)
        
        #ensure all layers share a common projection system (EPSG:32721)
        target_crs = QgsCoordinateReferenceSystem("EPSG:32721")
        
        reproj_xgb = processing.run(
            "native:reprojectlayer",
            {"INPUT" : xgb_fixed_layer, "TARGET_CRS": target_crs, "OUTPUT":"memory:"},
            context = context,
            feedback = feedback,
            is_child_algorithm = True,
            )["OUTPUT"]
        xgb_layer = QgsProcessingUtils.mapLayerFromString(reproj_xgb, context)
        
        reproj_simex = processing.run(
            "native:reprojectlayer",
            {"INPUT": simex_layer, "TARGET_CRS": target_crs, "OUTPUT": "memory:"},
            context = context,
            feedback = feedback,
            is_child_algorithm = True,
            )["OUTPUT"]
        simex_layer = QgsProcessingUtils.mapLayerFromString(reproj_simex, context)
        
        #rasterize XGBoost
        #filter to non-null polygons, burn in each field, combine into multi-band raster
        formula = '"n_0" IS NOT NULL'
        
        filter_xgb = processing.run(
            "native:extractbyexpression",
            {"INPUT": xgb_layer, "EXPRESSION": formula, "OUTPUT": "memory:"},
            context = context,
            feedback = feedback,
            is_child_algorithm = True,
            )["OUTPUT"]
        xgb_layer = QgsProcessingUtils.mapLayerFromString(filter_xgb, context)
        
        #use helper function to run rasterization
        xgb_fields = ["prob_brn", "prob_cvl", "prob_int", "pred", "purity"]
        extent = xgb_layer.extent()
        extent_string = f"{extent.xMinimum()},{extent.xMaximum()},{extent.yMinimum()},{extent.yMaximum()} [{xgb_layer.crs().authid()}]"
        pixel_size = 500
        
        raster_bands = [
            self.rasterize_field(xgb_layer, f, extent_string, pixel_size, context, feedback, "xgb")
            for f in xgb_fields
        ]
        
        #use helper function to stack into one multi-band raster
        xgb_layer = self.stack_bands(raster_bands, context, feedback, "xgb")
        
        #access user-defined year of analysis and retrieve only those SIMEX polygons
        year0 = self.parameterAsInt(parameters, self.YEAR, context)
        simex_formula = f' "Ano" = \'{year0}\' '
        
        filter_simex = processing.run(
            "native:extractbyexpression",
            {"INPUT": simex_layer, "EXPRESSION": simex_formula, "OUTPUT":"memory:"},
            context = context,
            feedback = feedback,
            is_child_algorithm = True,
            )["OUTPUT"]
        simex_layer = QgsProcessingUtils.mapLayerFromString(filter_simex, context)
        
        #construct the 'no logging' SIMEX polygon and combine with SIMEX polygons
        
        xgb_extent = processing.run(
            "native:extenttolayer",
            {"INPUT": extent_string, "OUTPUT": "memory:"},
            context = context, feedback = feedback, is_child_algorithm = True,
            )["OUTPUT"]
        xgb_extent_poly = QgsProcessingUtils.mapLayerFromString(xgb_extent, context)
        
        xgb_clip = processing.run(
            "native:clip",
            {"INPUT": xgb_extent_poly, "OVERLAY":xgb_fixed_layer,
            "OUTPUT": "memory:"},
            context = context, feedback = feedback, is_child_algorithm = True,
            )["OUTPUT"]
        xgb_extent_clipped = QgsProcessingUtils.mapLayerFromString(xgb_clip, context)
        
        simex_union = processing.run(
            "native:union",
            {"INPUT": xgb_extent_clipped, "OVERLAY": simex_layer, "OUTPUT": "memory:"},
            context = context, feedback = feedback, is_child_algorithm = True,
            )["OUTPUT"]
        simex_layer = QgsProcessingUtils.mapLayerFromString(simex_union, context)
        
        #create integer fields in SIMEX for rasterization
        simex_year = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": simex_layer,
                "FIELD_NAME":"Year",
                "FIELD_TYPE": 1, #integer
                "FIELD_LENGTH":5,
                "FIELD_PRECISION":0,
                "FORMULA": f'CASE WHEN "Ano" IS NULL THEN {year0} ELSE to_int("Ano") END',
                "OUTPUT":"memory:"
            },
            context = context, feedback = feedback, is_child_algorithm = True,
        )["OUTPUT"]
        simex_layer = QgsProcessingUtils.mapLayerFromString(simex_year, context)
        
        simex_legality = processing.run(
            "native:fieldcalculator",
            {
                "INPUT":simex_layer,
                "FIELD_NAME": "Legality",
                "FIELD_TYPE": 1,
                "FIELD_LENGTH": 5,
                "FIELD_PRECISION": 0,
                "FORMULA": (
                    'CASE '
                    'WHEN "Cate_tipo" IS NULL THEN -1 '
                    'WHEN "Cate_tipo" = \'Legal\' THEN 0 '
                    'WHEN "Cate_tipo" = \'Ilegal\' THEN 1 '
                    'ELSE -999 END'
                    ),
                "OUTPUT":"memory:"
            },
            context = context, feedback = feedback, is_child_algorithm = True,
        )["OUTPUT"]
        simex_layer = QgsProcessingUtils.mapLayerFromString(simex_legality, context)
        
        #rasterize simex polygons to two-band raster
        simex_fields = ["Year", "Legality"]
        extent = simex_layer.extent()
        extent_string = f"{extent.xMinimum()},{extent.xMaximum()},{extent.yMinimum()},{extent.yMaximum()} [{xgb_layer.crs().authid()}]"
        pixel_size = 500
        
        raster_bands = [
            self.rasterize_field(simex_layer, f, extent_string, pixel_size, context, feedback, "simex")
            for f in simex_fields
        ]
        
        #use helper function to stack into one multi-band raster
        simex_layer = self.stack_bands(raster_bands, context, feedback, "simex")
        
        #output raster(s)
        xgb_output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT1, context)
        shutil.copyfile(xgb_layer.source(), xgb_output_path)

        simex_output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT2, context)
        shutil.copyfile(simex_layer.source(), simex_output_path)
        
        # Send some information to the user
        feedback.pushInfo(f"XGB raster CRS: {xgb_layer.crs().authid()}")
        feedback.pushInfo(f"SIMEX raster CRS: {simex_layer.crs().authid()}")
        
        #BUILDING COMPARISON METRICS
        #obtain raster layer bands as arrays
        xgb = gdal.Open(xgb_output_path)
        xgb_pred_band = xgb.GetRasterBand(xgb_fields.index("pred") + 1)
        xgb_pred_array = xgb_pred_band.ReadAsArray()
        xgb_nodata = xgb_pred_band.GetNoDataValue()
        
        simex = gdal.Open(simex_output_path)
        simex_legality_band = simex.GetRasterBand(simex_fields.index("Legality") + 1)
        simex_legality_array = simex_legality_band.ReadAsArray()
        simex_nodata = simex_legality_band.GetNoDataValue()
        
        #check that rasters have same shape
        if xgb_pred_array.shape != simex_legality_array.shape:
            raise QgsProcessingException(f"Raster shapes dont match. XGB: {xgb_pred_array.shape} SIMEX: {simex_legality_array.shape}.")
        
        #mask out NoData and flatten
        valid_mask = (xgb_pred_array != xgb_nodata) & (simex_legality_array != simex_nodata)
        xgb_valid = xgb_pred_array[valid_mask]
        simex_valid = simex_legality_array[valid_mask]
        
        #build the agreement matrix
        xgb_burned = (xgb_valid == 0)
        xgb_logged = (xgb_valid == 1)
        xgb_intact = (xgb_valid == 2)
        simex_logging = (simex_valid != -1)
        
        n_00 = int((~simex_logging & xgb_intact).sum())     #intact agreement
        n_11 = int((simex_logging & xgb_logged).sum())     #logged agreement
        n_10 = int((simex_logging & xgb_intact).sum())      #simex logged, xgb no logged
        n_01 = int((~simex_logging & xgb_logged).sum())    #simex no logging, xgb logging
        
        agreement_df = pd.DataFrame(
            [[n_00, n_01], [n_10, n_11]],
            index = ["SIMEX No Logging", "SIMEX Logging"],
            columns = ["XGB Intact", "XGB Logged"],
        )
        agreement_df["Row Total"] = agreement_df.sum(axis = 1)
        agreement_df.loc["Column Total"] = agreement_df.sum(axis = 0)
        
        feedback.pushInfo(f"Agreement Matrix (Pixel Count): \n{agreement_df.to_string()}")
        
        #compute producer/user agreement. comission/omission
        total_pixels = n_00 + n_01 + n_10 + n_11
        
        prod_intact = n_00 / (n_00 + n_01)
        prod_logged = n_11 / (n_11 + n_10)
        omiss_intact = 1 - prod_intact
        omiss_logged = 1 - prod_logged
        
        user_intact = n_00 / (n_00 + n_10)
        user_logged = n_11 / (n_11 + n_01)
        commiss_intact = 1 - user_intact
        commiss_logged = 1 - user_logged
        
        feedback.pushInfo(
            f"Logging — Producer's: {prod_logged:.3f}, User's: {user_logged:.3f}, "
            f"Omission: {omiss_logged:.3f}, Commission: {commiss_logged:.3f}"
        )
        feedback.pushInfo(
            f"No logging — Producer's: {prod_intact:.3f}, User's: {user_intact:.3f}, "
            f"Omission: {omiss_intact:.3f}, Commission: {commiss_intact:.3f}"
        )
        
        #compute overall agreement and quantity/allocation disagreement
        overall_agreement = (n_00 + n_11) / total_pixels
        total_disagreement = 1 - overall_agreement
        feedback.pushInfo(f"Overall Agreement: {overall_agreement:.3f}")
        
        p00, p01, p10, p11 = n_00/total_pixels, n_01 / total_pixels, n_10 / total_pixels, n_11 / total_pixels
        simex_plogging = p10 + p11
        xgb_plogging = p01 + p11
        simex_pintact = p00 + p01
        xgb_pintact = p00 + p10
        
        quantity_logging = abs(simex_plogging - xgb_plogging)
        alloc_logging = 2 * min(simex_plogging - p11, xgb_plogging - p11)
        
        quantity_intact = abs(simex_pintact - xgb_pintact)
        alloc_intact = 2 * min(simex_pintact - p00, xgb_pintact - p00)
        
        quantity_disagreement = (quantity_logging + quantity_intact) / 2
        allocation_disagreement = (alloc_logging + alloc_intact) / 2
        
        feedback.pushInfo(
            f"Total disagreement: {total_disagreement:.3f} = "
            f"Quantity: {quantity_disagreement:.3f} + Allocation: {allocation_disagreement:.3f}"
        )
        
        #building the burned confusion matrix
        b0 = int((xgb_burned & ~simex_logging).sum())
        b1 = int((xgb_burned & simex_logging).sum())
        bT = b0 + b1
        burned_confusion = b1 / simex_logging.sum()
        
        burned_df = pd.DataFrame(
            [[b0], [b1], [bT]],
            index = ["SIMEX No Logging", "SIMEX Logging", "Total"],
            columns = ["XGB Burned"],
        )
        feedback.pushInfo(f"Burned Confusion Matrix (Pixel Count): \n{burned_df.to_string()}")
        feedback.pushInfo(f"Burned Confusion %: {burned_confusion}")
        
        #build agreement type map
        agreement_map_path = QgsProcessingUtils.generateTempFilename("agreement_map.tif")
        agreement_raster = processing.run(
            "gdal:rastercalculator",
            {
                "INPUT_A": xgb_output_path,
                "BAND_A": xgb_fields.index("pred") + 1,
                "INPUT_B": simex_output_path,
                "BAND_B": simex_fields.index("Legality") + 1,
                "FORMULA": (
                    "numpy.where((A == -999)|(B == -999), -999, "   #handle NoData pixels
                    "numpy.where((A == 1)&(B != -1), 1, "           #logging agreement
                    "numpy.where((A == 2)&(B == -1), 2, "           #intact agreement
                    "numpy.where((A == 2)&(B != -1), 3, "           #xgb intact, simex logging disagreement
                    "numpy.where((A == 1)&(B == -1), 4, "           #xgb logged, simex no logging disagreement
                    "numpy.where((A == 0)&(B != -1), 5, "           #xgb burned, simex logging
                    "6))))))"                                       #xgb burned, simex no logging
                ),
                "RTYPE": 1,
                "OUTPUT": agreement_map_path
            },
            context = context, feedback = feedback, is_child_algorithm = True,
        ) ["OUTPUT"]
        agreement_raster = QgsProcessingUtils.mapLayerFromString(agreement_raster, context)
        
        agreement_output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT3, context)
        shutil.copyfile(agreement_raster.source(), agreement_output_path)

        #compute agreement by legality
        simex_legal = (simex_valid == 0)
        simex_illegal = (simex_valid == 1)
        
        legal_intact = int((simex_legal & xgb_intact).sum())
        legal_logged = int((simex_legal & xgb_logged).sum())
        illegal_intact = int((simex_illegal & xgb_intact).sum())
        illegal_logged = int((simex_illegal & xgb_logged).sum())
        legal_total = legal_intact + legal_logged
        illegal_total = illegal_intact + illegal_logged
        
        legal_agreement = legal_logged / legal_total
        illegal_agreement = illegal_logged / illegal_total
        
        legality_df = pd.DataFrame(
            [[legal_intact, legal_logged, legal_total],
             [illegal_intact, illegal_logged, illegal_total]],
            index = ["SIMEX Legal", "SIMEX Illegal"],
            columns = ["XGB Intact", "XGB Logged", "Row Total"],
        )
        feedback.pushInfo(f"Legality Agreement Matrix (Pixel Count): \n{legality_df.to_string()}")
        feedback.pushInfo(f"Legal Agreement: {legal_agreement} \nIllegal Agreement: {illegal_agreement}")
        
        #
        
        # #create an output sink containing layers to display to the user
        # (sink, dest_id) = self.parameterAsSink(
        #     parameters,
        #     self.OUTPUT2,
        #     context,
        #     simex_layer.fields(),
        #     simex_layer.wkbType(),
        #     simex_layer.crs(),
        # )
        
        
#-------END MAIN PROCESSING ALGORITHM-------------------------------------------

        # #throw fatal error if no sink is created
        # if sink is None:
        #     raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT1))

        # # Compute the number of steps to display within the progress bar and
        # # get features from source
        # total = 100.0 / simex_layer.featureCount() if simex_layer.featureCount() else 0
        # features = simex_layer.getFeatures()

        # for current, feature in enumerate(features):
        #     # Stop the algorithm if cancel button has been clicked
        #     if feedback.isCanceled():
        #         break

        #     # Add a feature in the sink
        #     sink.addFeature(feature, QgsFeatureSink.Flag.FastInsert)

        #     # Update the progress bar
        #     feedback.setProgress(int(current * total))

        return {
            self.OUTPUT1: xgb_output_path,
            self.OUTPUT2: simex_output_path,
            self.OUTPUT3: agreement_output_path,
        }

    def createInstance(self):
        return self.__class__()
