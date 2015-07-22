NCGMP09 Metadata toolbox for ArcGIS 10.2

Contains tool useful for automating the writing of metadata for NCGMP09 geologic map ArcGIS geodatabases

- Create Glossary Stub
  Crawls through the feature classes and tables of an NCGMP09 geodatabase and writes a list of unique values within all controlled vocabulary fields to a Glossary table. Use this as a starting point for writing definitions for those controlled terms or join to other dictionary-like tables for calculating definitions.
  
- Metadata Updater
  Copies metadata elements as appropriate from a boilerplate template, a file of table (Entity) and field (Attributes) definitions, the DescriptionOfMapUnits, Glossary, and DataSources tables in an NCGMP09 geodatabase to CSDGM (FGDC) -compliant metadata documents for every feature class and table. 
  
To install:
-open up https://github.com/evanthoms/NGCMP09-metadata
-go to the lower right and click on Download Zip
-this will download the file NGCMP09-metadata-master.zip.
-extract the contents of that zip file to a suitable folder
-that will extract a folder called NCGMP09-metadata, a file called .gitattributes, .gitignore, and README.txt. You can delete the latter three files. They have nothing to do with the ArcGIS toolbox. They are only for the case where you want to collaborate on github.
-Go into NCGMP09 Metadata that is where you will see the .tbx file, a folder called docs and a folder called scripts. You need to keep all three of these things together within the same folder. You can move them where ever you like, but they have to stay together. 
-Now, in ArcToolbox, whether opened from ArcMap or ArcCatalog, you can right-click over some empty white space to get the context menu, and choose 'Add Toolbox'. Browse to NCGMP09 Metadata.tbx and select it.