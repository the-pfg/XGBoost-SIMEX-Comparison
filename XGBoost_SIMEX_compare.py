
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
)
from qgis import processing
import shutil

class XGBandSIMEXcompare(QgsProcessingAlgorithm):
    
    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.
    XGB_INPUT = "xgb_INPUT"
    SIMEX_INPUT = "simex_INPUT"
    YEAR = "YEAR"
    OUTPUT1 = "OUTPUT1"
    OUTPUT2 = "OUTPUT2"

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
            QgsProcessingParameterRasterDestination(self.OUTPUT1, "Output layer")
        )
        
        self.addParameter(
            QgsProcessingParameterRasterDestination(self.OUTPUT2, "Output layer 2")
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
            {"INPUT": raster_layers, "SEPARATE": True, "OUTPUT": file_path,},
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
        xgb_layer = context.takeResultLayer(xgb_fixed)
        
        simex_fixed = processing.run(
            "native:fixgeometries",
            {"INPUT": parameters[self.SIMEX_INPUT], "METHOD":1, "OUTPUT":"memory:"},
            context = context,
            feedback = feedback,
            is_child_algorithm = True,
            )["OUTPUT"]
        simex_layer = context.takeResultLayer(simex_fixed)
        
        #ensure all layers share a common projection system (EPSG:32721)
        target_crs = QgsCoordinateReferenceSystem("EPSG:32721")
        
        reproj_xgb = processing.run(
            "native:reprojectlayer",
            {"INPUT" : xgb_layer, "TARGET_CRS": target_crs, "OUTPUT":"memory:"},
            context = context,
            feedback = feedback,
            is_child_algorithm = True,
            )["OUTPUT"]
        xgb_layer = context.takeResultLayer(reproj_xgb)
        
        reproj_simex = processing.run(
            "native:reprojectlayer",
            {"INPUT": simex_layer, "TARGET_CRS": target_crs, "OUTPUT": "memory:"},
            context = context,
            feedback = feedback,
            is_child_algorithm = True,
            )["OUTPUT"]
        simex_layer = context.takeResultLayer(reproj_simex)
        
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
        xgb_layer = context.takeResultLayer(filter_xgb)
        
        #use helper function to run rasterization
        xgb_fields = ["n_0", "n_1", "n_2", "nT", "prob_brn", "prob_cvl", "prob_int", "pred", "nMax", "purity"]
        extent = xgb_layer.extent()
        extent_string = f"{extent.xMinimum()},{extent.xMaximum()},{extent.yMinimum()},{extent.yMaximum()} [{xgb_layer.crs().authid()}]"
        pixel_size = 500
        
        raster_bands = [
            self.rasterize_field(xgb_layer, f, extent_string, pixel_size, context, feedback, "xgb")
            for f in xgb_fields
        ]
        
        #use helper function to stack into one multi-band raster
        xgb_layer = self.stack_bands(raster_bands, context, feedback, "xgb")
        
        #access user-defined year of analysis and filter SIMEX to the year and the following year
        year0 = self.parameterAsInt(parameters, self.YEAR, context)
        simex_formula = f' "Ano" = \'{year0}\' '
        
        filter_simex = processing.run(
            "native:extractbyexpression",
            {"INPUT": simex_layer, "EXPRESSION": simex_formula, "OUTPUT":"memory:"},
            context = context,
            feedback = feedback,
            is_child_algorithm = True,
            )["OUTPUT"]
        simex_layer = context.takeResultLayer(filter_simex)
        
        
        
        
        #output raster(s)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT1, context)
        shutil.copyfile(xgb_layer.source(), output_path)

        # Send some information to the user
        feedback.pushInfo(f"CRS is {xgb_layer.crs().authid()}")
        
        
        #create an output sink containing layers to display to the user
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT2,
            context,
            simex_layer.fields(),
            simex_layer.wkbType(),
            simex_layer.crs(),
        )
        
        
#-------END MAIN PROCESSING ALGORITHM-------------------------------------------

        #throw fatal error if no sink is created
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT1))

        # Compute the number of steps to display within the progress bar and
        # get features from source
        total = 100.0 / simex_layer.featureCount() if simex_layer.featureCount() else 0
        features = simex_layer.getFeatures()

        for current, feature in enumerate(features):
            # Stop the algorithm if cancel button has been clicked
            if feedback.isCanceled():
                break

            # Add a feature in the sink
            sink.addFeature(feature, QgsFeatureSink.Flag.FastInsert)

            # Update the progress bar
            feedback.setProgress(int(current * total))

        
        # To run another Processing algorithm as part of this algorithm, you can use
        # processing.run(...). Make sure you pass the current context and feedback
        # to processing.run to ensure that all temporary layer outputs are available
        # to the executed algorithm, and that the executed algorithm can send feedback
        # reports to the user (and correctly handle cancellation and progress reports!)
        if False:
            buffered_layer = processing.run(
                "native:buffer",
                {
                    "INPUT": dest_id,
                    "DISTANCE": 1.5,
                    "SEGMENTS": 5,
                    "END_CAP_STYLE": 0,
                    "JOIN_STYLE": 0,
                    "MITER_LIMIT": 2,
                    "DISSOLVE": False,
                    "OUTPUT": "memory:",
                },
                context=context,
                feedback=feedback,
            )["OUTPUT"]

        # Return the results of the algorithm. In this case our only result is
        # the feature sink which contains the processed features, but some
        # algorithms may return multiple feature sinks, calculated numeric
        # statistics, etc. These should all be included in the returned
        # dictionary, with keys matching the feature corresponding parameter
        # or output names.
        return {self.OUTPUT1: output_path}

    def createInstance(self):
        return self.__class__()
