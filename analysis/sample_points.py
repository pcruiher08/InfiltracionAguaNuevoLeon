import sys, json; sys.path.insert(0,'.')
import ee
from pipeline import layers
from pipeline.config import DATASETS
layers.init()
col=ee.ImageCollection(DATASETS["burned"]).select("BurnDate")
scar=col.filterDate("2022-03-01","2022-06-01").max().gt(0).unmask(0).rename("scar")
img=ee.Image.cat([layers.scores(), layers.soil_moisture().rename("sm"), layers.slope_deg().rename("slope_deg"), scar]).updateMask(layers.valid_mask())
# estratificada: todos los pixeles quemados 2022 + muestra general
pts=img.sample(region=layers.aoi(),scale=500,numPixels=4500,seed=3,geometries=False)
rows=[f['properties'] for f in pts.getInfo()['features']]
json.dump(rows,open('analysis/sample.json','w'))
print(len(rows),'puntos',flush=True)
