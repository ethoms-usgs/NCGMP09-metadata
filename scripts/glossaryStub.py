#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:     
#
# Author:      ethoms
#
# Created:     17/04/2015
# Copyright:   (c) ethoms 2015
# Licence:     <your licence>
#-------------------------------------------------------------------------------
#!/usr/bin/env python

import arcpy
import sys
import os
             
def pPrint(text):
    print text
    arcpy.AddMessage(text)
    
gdb = sys.argv[1]

#gdb = r'C:\Workspace\MRP\Baranof\AA_PostZiglerEdits\ForPublication\BaranofIsland.gdb'

pPrint('Looking for controlled field terms in \n%s\n' % gdb)

controlledFields =["Type", "IdentityConfidence", "ExistenceConfidence", "GeneralLithology",
             "GeneralLithologyConfidence", "ParagraphStyle", "Property", "PropertyValue", 
             "Qualifier", "Event", "TimeScale", "Lithology", "ProportionValue", "ProportionTerm",
             "AgeUnits"]   

arcpy.env.workspace = gdb
#directory the gdb is in 
gdb_dir = os.path.dirname(gdb)

#get a list of the tables in the geodatabase
tables = []
for tab in arcpy.ListTables():
    tables.append(arcpy.Describe(tab).catalogPath)

#get a list of the feature datasets in the geodatabase
#when arcpy.env.workspace = arcpy.Describe(fd).catalogPath
#was used, only the first pass resulted in a full qualified
#path, the second time I only got the name of the dataset
#but if I make a list of the catalogPaths, I can pass those items to
#arcpy.env.workspace
datasets = []
for fd in arcpy.ListDatasets():
    datasets.append(arcpy.Describe(fd).catalogPath)

#run through the datasets and get a list of the feature classes
for fd in datasets:
    arcpy.env.workspace = fd
    for fc in arcpy.ListFeatureClasses():
        tables.append(arcpy.Describe(fc).catalogPath)

#run through the fields in the feature classes
#if any are in controlledFields, pull the values and find unique occurrences
#termList will be a dictionary formatted as term:(table, field)
termList = []
for t in tables:
    for fld in arcpy.ListFields(t):
        if fld.name in controlledFields:
            rows = arcpy.da.SearchCursor(t, fld.name)
            for row in rows:
                if not row[0] in termList and not row[0] == None and not row[0] == "":
                    s = "Term: {}, Table: {}, Field: {}".format(row[0], os.path.basename(t), fld.name)
                    pPrint(s)
                    termList.append(row[0])

arcpy.env.workspace = gdb
#get a list of the terms currently in the glossary
existingTerms = []
for et in arcpy.da.SearchCursor("Glossary", ["Term"]):
    existingTerms.append(et[0])

#open an insertCursor and add any new terms

cursor = arcpy.da.InsertCursor("Glossary", ["Term"])
for newTerm in termList:
    if not newTerm in existingTerms:
        pPrint("Adding {} to Glossary".format(newTerm))
        cursor.insertRow([newTerm])
    
pPrint("\nDone")

del cursor
            

        

