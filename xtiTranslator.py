import lxml.etree as etree
import argparse
import re
import string
'''XTI Translator
A. Wallace

A few functions to help the tireless PLC engineer build all the
variable lists from their fieldbus topology.

Uses an exported xti file to formulate a list of Q's and I's with
the correct types that can be copied directly into a Global IO list
in the PLC code. This used to be generated by hand...

Also adds a pragma instruction to link the IO variable declaration
back to the hardware IO point.
'''

'''
parser = argparse.ArgumentParser(description='Turns .xti files into variable lists for the PLC')
parser.add_argument('filename', metavar='DIR', help='Filepath to the xti file', nargs=1)

args = parser.parse_args()
'''
   

translationList = [ ('Analog output','AO'), ('BIT', 'BOOL'), ('Channel','Ch') ]
def TranslateName(name, translationList=translationList):
    '''Translate names to a compressed format, using PLC legal characters
    '''
    for k,v in translationList:
        name = name.replace(k,v)

    name = string.capwords(name)
    name.replace(' ', '_')
    return name

#A list of reg expressions to search for stuff to delete
excludeBoxList = [ 'E[LP][5-9]\d3' ]
def CleanBoxes(root, exList=excludeBoxList, vlvl=0):
    """Creates the iterable of boxes in the topology while
    excluding all boxes on the exList.

    exList = a list of re to exclude
    root = the root of the xti xml tree (xml.etree.ElementTree.ElementTree object) 
    """
    boxes = root.findall('.//Box')
    if vlvl > 1: print 'type',type(boxes),'stuff',boxes
    for box in reversed(boxes):
        name = box.find('Name')
        if vlvl>1: print 'Checking box:',name.text
        for exclusion in exList:
            if re.search(exclusion, name.text):
                if vlvl>1: print 'Removing box:',name.text
                box.getparent().remove(box)
                break
    return root

def PrintTopology(root, level=0):
    '''Prints the topo of the PDOs in the xti'''
    boxes = root.findall('.//Box')
    if len(boxes):
        for box in boxes:
            print '---------------'
            #Box names
            print '#',box.find('Name').text
            #Pdos
            if level > 1:
                pdos = box.findall('./EtherCAT/Pdo')
                for pdo in pdos:
                    print '|-->',TranslateName(pdo.get('Name'))
                    entries = pdo.findall('./Entry')
                    for entry in entries:
                            print '   |-->',TranslateName(entry.get('Name')),entry.find('Type').text
    return

omit_list = [ 'Compact', 'Status', 'None'] 
def SimplifyPdos(root, omit_list=omit_list, vlvl=0):
    ''' Removes unessecary PDOs
    If a pdo name attribute is found to have a word in the omit list, the child with
    that attribute is removed.
    
    boxes = the tree object
    omit_list = list of words in child node name attributes to look for, can be re
    '''
    boxes = root.findall('.//Box')
    for box in boxes:
        name = box.find('Name')
        if vlvl > 0: print 'Cleaning up box: ', name.text
        #Do PDOs first
        pdos = box.findall('.//Pdo')
        for pdo in reversed(pdos):
            pdoName = pdo.get('Name','None')
            if vlvl >2: print 'Checking pdo..: ',pdoName
            for omission in omit_list:
                if re.search(omission, pdoName):
                    if vlvl >1: print 'Removing child: ',pdoName
                    pdo.getparent().remove(pdo)
                    break
        entries = box.findall('.//Entry')
        for entry in reversed(entries):
            entryName = entry.get('Name','None')
            if vlvl > 2: print 'Checking entry: ',entryName
            for omission in omit_list:
                if re.search(omission, entryName):
                    if vlvl >1: print 'Removing child: ',entryName
                    entry.getparent().remove(entry)
                    break
                    
    return root

def MakeLinkPragma(element, vlvl=0):
    '''Makes the link pragma instruction'''
    linkList = [element.get('Name')]
    for ancestor in element.iterancestors('Pdo','Entry','Box','Device'):
        if ancestor.tag == 'Entry' or ancestor.tag =='Pdo':
            linkList.append(ancestor.get('Name'))
        elif ancestor.tag =='Device' or ancestor.tag =='Box':
            linkList.append(ancestor.find('Name').text)
        else:
            print 'Didn\'t find any ancestors'
        if vlvl > 1: print 'Adding',linkList[-1]
    linkAssembly = 'TIID'
    for link in reversed(linkList):
           linkAssembly = linkAssembly + '^' + link
    pragma = '{{ attribute \'TcLinkTo\':=\'{link}\'}}'.format(link=linkAssembly)
    return pragma

def IsIQ(name, simulator=False):
    ''' Determines if you should use Q or I
    simulator = flips the I and Q for use in the simulator code'''
    out = ''
    if name == None:
        return '?'
    elif re.search('Input|Ai|Value', name):
        if simulator: 
            out = 'Q' 
        else: out = 'I'
        return out
    elif re.search('Output|Ao|output', name):
        if simulator: out = 'I'
        else: out = 'Q'
        return out
    else:
        return '?'

def IQList(root, vlvl=0):
    boxes = root.findall('.//Box')
    formatBoxName = re.compile('(?P<term>.+)\((?P<other>\w+)(?:-.*)?\)')
    formatPDOName = re.compile('.*Channel (.+)')
    iqList = []
    for box in boxes:
        boxName = box.find('Name').text
        if vlvl > 2: print 'Working on box',boxName
        if re.search('EK1.+', boxName): 
            if vlvl > 1: print 'Found EK1*, skipping'
            continue
        boxName = formatBoxName.sub(r'\1_\2', boxName).replace(' ','')
        iqList.append('//'+boxName)
        pdos = box.findall('.//Pdo')
        for pdo in pdos:
            pdoName = pdo.get('Name')
            if vlvl > 2: print 'Working on pdo',pdoName
            pdoName = formatPDOName.sub(r'Ch\1', pdoName)
            entries = pdo.findall('Entry')
            for entry in entries:
                entryName = entry.get('Name')
                if vlvl > 2: print 'Working on entry',entryName
                entryType= entry.find('Type').text
                #Each iq line printed here
                pragmaLine = MakeLinkPragma(entry)
                entryLine = '{iq}_{boxname}_{pdoname} AT %{iq}* : {entrytype};'.format(boxname = boxName,
                                                                                         pdoname = pdoName,
                                                                                         entryname = TranslateName(entryName),
                                                                                         iq = IsIQ(entryName),
                                                                                         entrytype = TranslateName(entryType))
                if vlvl > 1: print 'Adding',entryLine
                iqList.append(pragmaLine)
                iqList.append(entryLine)
                
    return iqList

if __name__=="__main__":
    filename='GA.xti'
    tree = etree.parse(filename)
    root = tree.getroot()

    inputs = root.findall(".//Vars[@VarGrpType='1']/Var")
    outputs = root.findall(".//Vars[@VarGrpType='2']/Var")

    for element in inputs:
        print element.find('Name').text + ' AT %I*  :  '+ element.find('Type').text + ';'

    for element in outputs:
        print element.find('Name').text + ' AT %Q*  :  '+ element.find('Type').text + ';'       
                    
    
    
