#-------------------------------------------------------------------------------
# Name:        ncgmp09_update_md.python
#              MNCGMP09 Metadata Updater
# Purpose:     Takes an NCGMP09 geodatabase:
#              1) exports an FGDC metadata file in XML for every feature class and 
#                 standalone table
#              2) Updates the Entity Domain Value, Entity Domain Definition, and 
#                 Entity Domain Definition Source elements in each XML file for each controlled field from 
#                 values in the Glossary table, an NCGMP09-required table
#              3) Optionally, takes a prepared template XML file with metadata elements you want migrated to all
#                 records ('idinfo', 'dataqual', 'distinfo', 'metainfo') and copies them to all XML files.
#              4) Optionally, takes a prepared XML file of NCGMP09 field names and definitions
#                 and uses those values to update the Attribute Label, Attribute Definition, and Attribute
#                 Definition Source elements for any NCGMP09 field in any of the XML files. The file /docs/NCGMP09_field_definitions.xml
#                 can be edited to include any number of extra fields that might be in your geodatabases
#              5) Requires well-formed NCGMP09 v 1.1 Glossary and DataSources tables.
#
# Author:      ethoms
#
# Created:     17/04/2015
# Copyright:   no copyright
# Licence:     Creative Commons
#-------------------------------------------------------------------------------
#!/usr/bin/env python

import arcpy
import os
import sys
from xml.dom.minidom import *
import glob
import xml.etree.ElementTree as ET
import copy
from subprocess import call

#*****************************************************************************
def pPrint(text):
    """Print to the interactive screen and to geoprocessing results"""
	
    print text
    arcpy.AddMessage(text)
    
    
def buildWhereClause(table, field, value):
    """Constructs a SQL WHERE clause to select rows having the specified value
    within a given field and table. Uses field delimiters to determine the proper
    syntax for any data source and field type"""

    # Add DBMS-specific field delimiters
    fieldDelimited = arcpy.AddFieldDelimiters(table, field)

    # Determine field type
    fieldType = arcpy.ListFields(table, field)[0].type

    # Add single-quotes for string field values
    if str(fieldType) == 'String':
        value = "'%s'" % value

    # Format WHERE clause
    whereClause = "%s = %s" % (fieldDelimited, value)
    return whereClause
    
def tableList(gdb):   
    """"Returns a list of (name, catalog path) tuples for all tables and feature classes in an ESRI gdb"""
	
    arcpy.env.workspace = gdb
    tables = []
    
    #get a list of the standalone tables in the geodatabase
    for tab in arcpy.ListTables():
        desc = arcpy.Describe(tab)
        tables.append([desc.name, desc.catalogPath])
    
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
            desc = arcpy.Describe(fc)
            tables.append([desc.name, desc.catalogPath])
    return tables

def exportMD(gdb):   
    """"Export FGDC XML metadata file for each gdb object
        Collect a list of the paths to these files for later use"""
    xmls = []
    #objList is a list of all feature classes and standalone tables and their paths
    for dsPath in tableList(gdb):
        table = dsPath[0] #name of the table
        path = dsPath[1]  #catalogPath of the table
        fXML = os.path.join(outDir, table + '.xml')
        if os.path.exists(fXML):
            os.remove(fXML)
			
       #won't work when run outside of ArcCatalog or ArcMap for some reason!!!
        #arcpy.USGSMPTranslator_conversion(path, '', 'XML', fXML)
        arcpy.ExportMetadata_conversion(path, translator, fXML)
        xmls.append(fXML)

        pPrint('%s has been created' % fXML)
		
    return xmls

def importMD(gdb): 
    """Import XML back into the target feature class or table."""
    for dsPath in tableList(gdb):
        table = dsPath[0]
        target = dsPath[1]
        source = os.path.join(outDir, table + '.xml')
        if os.path.exists(source):
            pPrint(source)
            arcpy.ImportMetadata_conversion(source, "FROM_FGDC", target)
        else:
            pPrint("Could not find a metadata file for \n %s" % target)
    
def parentFolder(gdbPath):  
    """Return the parent folder path of an ArcCatalog object.
       Queries dataType because objects within feature datasets have paths
       which are delimited as if they were system folders when they are not"""
	
    pFolder = gdbPath
    while not arcpy.Describe(pFolder).dataType =='Folder':
        pFolder = os.path.split(pFolder)[0]
    return pFolder

def fieldNameList(table):    
    """Returns a list of field names from input table that are also in the list of NCGMP09 controlled fields"""
	
    fldList = arcpy.ListFields(table)
    nameList = []
    for fld in fldList:
        if fld.name in controlledFields:
            nameList.append(fld.name)
    return nameList

def findSourceRef(sourceID):
    """Finds the source reference for each DataSource_ID"""
	
    query = buildWhereClause(dataSources, "DataSources_ID", sourceID)
    rows = arcpy.da.SearchCursor(dataSources, ["Source"], query)
    try:
        row = rows.next()
        return row[0]
    except:
        return ""

def updateDomains(table, fldList, fcXML):
    """1) Finds all controlled-vocabulary fields in the table sent to it
       2) Builds a set of unique terms in each field, ie, the domain
       3) Matches each domain value to an entry in the glossary
       4) Builds a dictionary of term:(definition, source) items
       5) Takes the dictionary items and put them into the metadata
          document as Attribute_Domain_Values"""
    dom = parse(fcXML)
    
    #for each field in fldList (controlled fields)
    pPrint('Adding values, definitions, data sources in %s for the following fields:' % fcXML)
    for fld in fldList:
        pPrint('\t%s' % fld)
        termList = []
        for row in arcpy.da.SearchCursor(table, [fld]):
            if not row[0] in termList and not row[0] == None and not row[0] == "":
                termList.append(row[0])
                
        #create an empty dictionary object to hold the matches between the unique terms
        #and their definitions (grabbed from the glossary)
        defs = {}
        cantfind = []
        
        #for each unique term, try to create a search cursor of just one record where the term
        #matchs a Term field value from the glossary
        #Map Units are a special case because their definition is not in the Glossary but the DMU
        if fld == 'MapUnit':
            for unit in termList:
                query = buildWhereClause(DMU, fld, unit)
                rows = arcpy.da.SearchCursor(DMU, ["FullName", "DescriptionSourceID"], query)
                try:
                    row = rows.next()
                    #create an entry in the dictionary of term:[definition, source] key:value pairs
                    #this is how we will enumerate through the enumerated_domain section
                    defs[unit] = []
                    defs[unit].append(row[0])
                    defs[unit].append(findSourceRef(row[1]))
                    
                #otherwise, add the term to the cantfind list 
                except:
                    cantfind.append(unit)
        elif fld == 'DataSourceID':
            for das in termList:
                query = buildWhereClause(dataSources, 'DataSources_ID', das)
                rows = arcpy.da.SearchCursor(dataSources, ["DataSources_ID", "Source"], query)
                try:
                    row = rows.next()
                    #create an entry in the dictionary of term:[definition, source] key:value pairs
                    #this is how we will enumerate through the enumerated_domain section
                    defs[das] = []
                    defs[das].append(row[1])
                    defs[das].append('This study')
                    
                #otherwise, add the term to the cantfind list 
                except:
                    cantfind.append(das)                
        else:
            for term in termList:
                #pull a term from the values in the controlled field
                query = buildWhereClause(glossary, "Term", term)
                #search for that term in the Glossary
                rows = arcpy.da.SearchCursor(glossary, ["Definition", "DefinitionSourceID"], query)

                #Create an entry in the dictionary of term:[definition, source] key:value pairs
                #this is how we will enumerate through the enumerated_domain section
                try:
                    row = rows.next()
                    defs[term] = []
                    defs[term].append(row[0])
                    defs[term].append(findSourceRef(row[1]))
                    
                #otherwise, add the term to the cantfind list 
                except:
                    cantfind.append(term)
                
        #pPrint(cantfind)
    
        if not len(cantfind) == 0:
            pPrint('\t\tCannot find definition(s) for the following term(s):')
            pPrint('\t\t'.join(cantfind))
        else:
           pPrint('\t\tAll terms are defined in the metadata')

        #write these definitions to the XML tree
        #work on this
        #root = ET.parse(fcXML).getroot()
        #tree = ET.ElementTree(writeFieldDomain(fld, defs, dom))
        
        dom = writeFieldDomain(fld, defs, dom)
                
        #save the xml file
        dom.saveXML
        outf = open(fcXML, 'w')
        dom.writexml(outf)
        outf.close()
    
def writeFieldDomain(fld, defs, dom):  
    """Write the term:(definition, source) items to elements in the metadata XML.
       Currently uses xml.dom.minidom. Should update this to ElementTree!"""
    ##element tag names are
    ## attr             = Attribute
    ## attrlabl         = Attribute_Label
    ## attrdomv         = Attribute_Domain_Values
    ## edom             = Enumerated_Domain
    ## edomv            = Enumerated_Domain_Value
    ## edomd            = Enumerated_Domain_Definition
    ## edomvds          = Enumerated_Domain_Value_Definition_Source
    sorted(defs)
    labelNodes = dom.getElementsByTagName('attrlabl')
    for attrlabl in labelNodes:
        if attrlabl.firstChild.data == fld:
            attr = attrlabl.parentNode
            #if attrdomv exists in this node, remove it.
            #it would get written there because there is a placeholder for it in 
            #NCGMP09_entity_definitions.xml in case no enumerated domain values are found
            if not len(attr.getElementsByTagName('attrdomv')) == 0:
                attr.removeChild(attr.getElementsByTagName('attrdomv')[0])
             
            #attrdomv = dom.createElement('attrdomv')
            #for k in defs.iteritems():
            for key in sorted(defs):
                edom = dom.createElement('edom')
                        
                edomv = dom.createElement('edomv')
                #edomvText = dom.createTextNode(k[0])
                edomvText = dom.createTextNode(key)
                edomv.appendChild(edomvText)
        
                edomvd = dom.createElement('edomvd')
                #edomvdText = dom.createTextNode(k[1][0])
                edomvdText = dom.createTextNode(defs[key][0])
                edomvd.appendChild(edomvdText)
                                
                edomvds = dom.createElement('edomvds')
                #edomvdsText = dom.createTextNode(k[1][1])
                edomvdsText = dom.createTextNode(defs[key][1])
                edomvds.appendChild(edomvdsText)
        
                edom.appendChild(edomv)
                edom.appendChild(edomvd)
                edom.appendChild(edomvds)
                
                #append enumerated domain to an attribute domain values node
                attrdomv = dom.createElement('attrdomv')
                attrdomv.appendChild(edom)
                
                # append attribute domain values node to attribute node
                attr.appendChild(attrdomv)
                
            # #if attrdomv exists in this node, replace it
            # if not len(attr.getElementsByTagName('attrdomv')) == 0:
                # attr.replaceChild(attrdomv, attr.getElementsByTagName('attrdomv')[0])
            # #else append it
            # else:
                # attr.appendChild(attrdomv)
                
    return dom
                
def addAttributeDomains():  
    """Control flow function for exporting metadata and updating field domains"""

    #For each table in the list, collect the name, the list of controlled fields, and then
    #populate the attribute domains from the Glossary
    for dsPath in tableList(gdb):
        table = dsPath[0]
        path = dsPath[1]
		
		#get a list of the fields in this table that are in the NCGMP09
        #controlled fields list. Send the function the full catalog path
        #just to be sure it can be located
        #Should we get this list from the exported XML with ElementTree instead
        #of arcpy? Would probably be faster...
        fldNameList = fieldNameList(path)
        
		#we JUST made an xml file for this object so the file had better be there!
        mdXML = os.path.join(outDir, table + '.xml')
		
        #update the 'domains' (entity, attribute pairs for those controlled fields)
        updateDomains(path, fldNameList, mdXML)

def addTemplateItems():
    """Takes a list of metadata elements from a template XML and migrates 
       them to all FGDC metadata XML files in the output folder"""

    #qPath = os.path.join(outDir, '*.xml')
    #xmls = glob.glob(qPath)
	
	#create the template document
    tempDoc = ET.parse(template)

	#go through the exported XML files
    for x in xmlList:
        fName = os.path.splitext(os.path.basename(x))[0]
        GDB = os.path.basename(gdb)
        root = ET.parse(x).getroot()
        if root.tag == 'metadata':
            #remove the existing elements
            for elementName in templateElements:
                #if root.find(elementName) is not None:
                if root.find(elementName): 
                    root.remove(root.find(elementName))

                #now insert the copies from the template
                #need to go trough one by one because two of the elements we insert by index
                #and the other two we simply append in order to maintain the FGDC order
                copyElem = copy.deepcopy(tempDoc.find(elementName))
                if elementName == 'idinfo':
                    root.insert(0, copyElem)
                    title = list(copyElem.iter('title'))[0]
                    title.text = 'Metadata for %s in %s' % (fName, GDB) 
                elif elementName == 'dataqual':
                    root.insert(1, copyElem)
                elif elementName == 'distinfo':
                    root.append(copyElem)
                elif elementName == 'metainfo':
                    root.append(copyElem)
        else:
            pPrint('%s\ndoes not appear to be a metadata file!' % x)
            raise SystemError
            
        tree = ET.ElementTree(root)
        #pPrint(ET.dump(tree))
        #pPrint(os.path.join(outDir, x))
        tree.write(os.path.join(outDir, x))
		
def getElementDictionary(elemIter):
    """Makes a dictionary of {Entity or Attribute label: Entity or Attribute element} for items from NCGMP09_field_definitions
       Must be passed a variable created by Element.iter(<value>)"""
    elemDict = {}
    for elem in elemIter:
        childDict = {}
        entity = elem.find('enttyp')
        label = entity[0].text
        childDict[label] = entity
        children = elem.iter('attr')
        for child in children:
            childDict[child[0].text] = child
        elemDict[label] = childDict
    return elemDict

def addTableFieldDefinitions():
    """Add table and field definitions for (mostly) NCGMP09 controlled tables and fields
       User may add their own definitions for tables and fields which they have added by 
       modifying /docs/NCGMP09_field_definitions.xml"""

    #Start by making a dictionary of table names where the definitions are the element objects so that we
    #can easily search on table name and get a valid ElementTree element to copy later
    defsDoc = ET.parse(NCGMP09_defs)
    tDets = defsDoc.iter('detailed')
    tDefsDict = getElementDictionary(tDets)

    #Now go through newly exported XML files:
    for f in xmlList:
        pPrint('Looking in the template file for table and field definitions to add to: \n\t%s' % f)
        #make an ElementTree
        root = ET.parse(f).getroot()
        #find the enttyp element - there 'should' be only one per feature class or table metadata record
        #but we'll iterate in case there are more
        fDets = root.iter('detailed')
        for fDet in fDets:
            entity = fDet.find('enttyp')
            label = entity[0].text
            #if there is a match between this entity.text and a key in the dictionary then we have a table 
            #definition in the template file
            if label in tDefsDict.keys():
                #remove the entity/table element and swap in the one from the dictionary
                pPrint('\tUpdating the definition for: \n\t\t%s' % label)
                i = list(fDet).index(entity)
                fDet.remove(entity)
                copyElem = copy.deepcopy(tDefsDict[label][label])
                fDet.insert(i, copyElem)
                #now find all matching fields within this table/entity element
                atts = fDet.iter('attr')
                for att in atts:
                    attLabel = att[0].text
                    if attLabel in tDefsDict[label].keys():
                        pPrint('\t\t%s' % attLabel)
                        i = list(fDet).index(att)
                        fDet.remove(att)
                        copyElem = copy.deepcopy(tDefsDict[label][att[0].text])
                        fDet.insert(i, copyElem)
            
        tree = ET.ElementTree(root)
        tree.write(f)
        
def mpXML():
    for f in xmlList:
        fName = os.path.splitext(os.path.basename(f))[0]
        outPath = os.path.join(outDir, fName + '_err.txt')
        call([mp, '-e', outPath, f])
        
def mpTXT():
    for f in xmlList:
        fName = os.path.splitext(os.path.basename(f))[0]
        outPath = os.path.join(outDir, fName + '_meta.txt')
        call([mp, '-t', outPath, f])
        
def mpFAQ():
    for f in xmlList:
        fName = os.path.splitext(os.path.basename(f))[0]
        outPath = os.path.join(outDir, fName + '_faq.html')
        call([mp, '-f', outPath, f])
        
def mpHTML():
    for f in xmlList:
        fName = os.path.splitext(os.path.basename(f))[0]
        outPath = os.path.join(outDir, fName + '_meta.html')
        call([mp, '-h', outPath, f])

#precondition
validate = False

#Parameters and start
gdb = sys.argv[1]       #path
template = sys.argv[2]  #path
addDefs = sys.argv[3]   #true or false
validate = sys.argv[4]	#true or false
outList = sys.argv[5]
outDir = sys.argv[6]	#path

#global variables
arcpy.env.workspace = gdb
gdbFolder = parentFolder(gdb)
glossary = os.path.join(gdb, 'Glossary')
dataSources = os.path.join(gdb, 'DataSources')
DMU = os.path.join(gdb, 'DescriptionOfMapUnits')
parentFolder = os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0])))
docs = os.path.join(parentFolder, 'docs')
NCGMP09_defs = os.path.join(docs, 'NCGMP09_entity_definitions.xml')
translator = os.path.join(docs, 'ARCGIS2FGDC.xml')
mp = os.path.join(docs, 'mp.exe')

controlledFields =["Type", "MapUnit", "IdentityConfidence", "ExistenceConfidence", "GeneralLithology",
             "GeneralLithologyConfidence", "ParagraphStyle", "Property", "PropertyValue", 
             "Qualifier", "Event", "TimeScale", "Lithology", "ProportionValue", "ProportionTerm",
             "AgeUnits", "DataSourceID"]

			 
fcIndex = {'idinfo':0, 'dataqual':1, 'spdoinfo':2, 'spref':3, 'eainfo':4, 'distinfo':5, 'metainfo':6}
tabIndex = {'idinfo':0, 'dataqual':1, 'eainfo':2, 'distinfo':3, 'metainfo':4}
templateElements = ['idinfo', 'dataqual', 'distinfo', 'metainfo']

pPrint('NCGMP09_update_md.py')
pPrint('Geodatabase: %s' % gdb)

#First, export metadata files for all objects in the geodatabase,
#feature datasets excluded. Get the list of full paths to these files as xmlList
xmlList = exportMD(gdb)
xmlListcopy = xmlList

#if the user wants table and field definitions:
if addDefs:
    #Create a couple global variables we don't need outside of this option
    addTableFieldDefinitions()

#add attribute domain values to the XML files from the Glossary
addAttributeDomains()
pPrint("Attributes domains added")
#if a template XML was provided, update the newly exported XML files
if template:
    addTemplateItems()
    
#import the xml files back in to the source feature classes and standalone tables
importMD(gdb)

#if the user wants the new xmls files validated
if validate:
    mpXML()

#if the user wants a plain text version of the metadata
if 'TXT' in outList:
    mpTXT()    

#if the user wants an HTML version of the metadata
if 'HTML' in outList:
    mpHTML()
    
#if the user wants an FAQ-formed HTML file
if 'FAQ' in outList:
    mpFAQ()

pPrint('Done!')