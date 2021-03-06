import aes128
import Title
import Titles
import Hex
import math
from binascii import hexlify as hx, unhexlify as uhx
from struct import pack as pk, unpack as upk
from hashlib import sha256
import Fs.Type
import os
import re
import pathlib
import Keys
import Config
import Print
import Nsps
from tqdm import tqdm
import Fs
from Fs.File import File
from Fs.Rom import Rom
from Fs.Pfs0 import Pfs0
from Fs.BaseFs import BaseFs
from Fs.Ticket import Ticket

MEDIA_SIZE = 0x200


class SectionTableEntry:
	def __init__(self, d):
		self.mediaOffset = int.from_bytes(d[0x0:0x4], byteorder='little', signed=False)
		self.mediaEndOffset = int.from_bytes(d[0x4:0x8], byteorder='little', signed=False)
		
		self.offset = self.mediaOffset * MEDIA_SIZE
		self.endOffset = self.mediaEndOffset * MEDIA_SIZE
		
		self.unknown1 = int.from_bytes(d[0x8:0xc], byteorder='little', signed=False)
		self.unknown2 = int.from_bytes(d[0xc:0x10], byteorder='little', signed=False)
		self.sha1 = None
		
	
def GetSectionFilesystem(buffer, cryptoKey):
	fsType = buffer[0x3]
	if fsType == Fs.Type.Fs.PFS0:
		return Fs.Pfs0(buffer, cryptoKey = cryptoKey)
		
	if fsType == Fs.Type.Fs.ROMFS:
		return Fs.Rom(buffer, cryptoKey = cryptoKey)
		
	return BaseFs(buffer, cryptoKey = cryptoKey)
	
class NcaHeader(File):
	def __init__(self, path = None, mode = None, cryptoType = -1, cryptoKey = -1, cryptoCounter = -1):
		self.signature1 = None
		self.signature2 = None
		self.magic = None
		self.isGameCard = None
		self.contentType = None
		self.cryptoType = None
		self.keyIndex = None
		self.size = None
		self.titleId = None
		self.sdkVersion = None
		self.cryptoType2 = None
		self.rightsId = None
		self.titleKeyDec = None
		self.masterKey = None
		self.sectionTables = []
		self.keys = []
		
		super(NcaHeader, self).__init__(path, mode, cryptoType, cryptoKey, cryptoCounter)
		
	def open(self, file = None, mode = 'rb', cryptoType = -1, cryptoKey = -1, cryptoCounter = -1):
		super(NcaHeader, self).open(file, mode, cryptoType, cryptoKey, cryptoCounter)
		self.rewind()
		self.signature1 = self.read(0x100)
		self.signature2 = self.read(0x100)
		self.magic = self.read(0x4)
		self.isGameCard = self.readInt8()
		self.contentType = self.readInt8()

		try:
			self.contentType = Fs.Type.Content(self.contentType)
		except:
			pass

		self.cryptoType = self.readInt8()
		self.keyIndex = self.readInt8()
		self.size = self.readInt64()
		self.titleId = hx(self.read(8)[::-1]).decode('utf-8').upper()
		
		self.readInt32() # padding
		

		self.sdkVersion = self.readInt32()
		self.cryptoType2 = self.readInt8()
		
		self.read(0xF) # padding
		
		self.rightsId = hx(self.read(0x10))
		
		if self.magic not in [b'NCA3', b'NCA2']:
			raise Exception('Failed to decrypt NCA header: ' + str(self.magic))
		
		self.sectionHashes = []
		
		for i in range(4):
			self.sectionTables.append(SectionTableEntry(self.read(0x10)))
			
		for i in range(4):
			self.sectionHashes.append(self.sectionTables[i])

		self.masterKey = (self.cryptoType if self.cryptoType > self.cryptoType2 else self.cryptoType2)-1

		if self.masterKey < 0:
			self.masterKey = 0
		
		
		self.encKeyBlock = self.getKeyBlock()
		#for i in range(4):
		#	offset = i * 0x10
		#	key = encKeyBlock[offset:offset+0x10]
		#	Print.info('enc %d: %s' % (i, hx(key)))

		if Keys.keyAreaKey(self.masterKey, self.keyIndex):
			crypto = aes128.AESECB(Keys.keyAreaKey(self.masterKey, self.keyIndex))
			self.keyBlock = crypto.decrypt(self.encKeyBlock)
			self.keys = []
			for i in range(4):
				offset = i * 0x10
				key = self.keyBlock[offset:offset+0x10]
				#Print.info('dec %d: %s' % (i, hx(key)))
				self.keys.append(key)
		else:
			self.keys = [None, None, None, None, None, None, None]
		

		if self.hasTitleRights():
			if self.titleId.upper() in Titles.keys() and Titles.get(self.titleId.upper()).key:
				self.titleKeyDec = Keys.decryptTitleKey(uhx(Titles.get(self.titleId.upper()).key), self.masterKey)
			else:
				pass
				#Print.info('could not find title key!')
		else:
			self.titleKeyDec = self.key()

	def key(self):
		return self.keys[2]
		return self.keys[self.cryptoType]

	def hasTitleRights(self):
		return self.rightsId != (b'0' * 32)

	def getKeyBlock(self):
		self.seek(0x300)
		return self.read(0x40)

	def setKeyBlock(self, value):
		if len(value) != 0x40:
			raise IOError('invalid keyblock size')

		self.seek(0x300)
		return self.write(value)

	def getCryptoType(self):
		self.seek(0x206)
		return self.readInt8()

	def setCryptoType(self, value):
		self.seek(0x206)
		self.writeInt8(value)
		
	def setgamecard(self, value):
		self.seek(0x204)
		self.writeInt8(value)
		
	def getgamecard(self):
		self.seek(0x204)
		return self.readInt8()

	def getCryptoType2(self):
		self.seek(0x220)
		return self.readInt8()

	def setCryptoType2(self, value):
		self.seek(0x220)
		self.writeInt8(value)

	def getRightsId(self):
		self.seek(0x230)
		return self.readInt128('big')

	def setRightsId(self, value):
		self.seek(0x230)
		self.writeInt128(value, 'big')

	def setRightsId(self, value):
		self.seek(0x230)
		self.writeInt128(value, 'big')	
			
	def get_hblock_hash(self):
		self.seek(0x280)
		return self.read(0x20)
		
	def set_hblock_hash(self, value):
		self.seek(0x280)
		return self.write(value)		

	def calculate_hblock_hash(self):
		indent = 2
		tabs = '\t' * indent
		self.seek(0x400)
		hblock = self.read(0x200)	 
		sha=sha256(hblock).hexdigest()		
		sha_hash= bytes.fromhex(sha)
		Print.info(tabs + 'calculated header block hash: ' + str(hx(sha_hash)))
		return sha_hash 
		
	def get_hblock_version(self):
		self.seek(0x400)
		return self.read(0x02)	
		
	def get_hblock_filesystem(self):
		self.seek(0x403)
		return self.read(0x01)	

	def get_hblock_hash_type(self):
		self.seek(0x404)
		return self.read(0x01)	
		
	def get_hblock_crypto_type(self):
		self.seek(0x405)
		return self.read(0x01)	
		
	def get_htable_hash(self):
		self.seek(0x408)
		return self.read(0x20)	

	def set_htable_hash(self, value):
		self.seek(0x408)
		return self.write(value)		
	
	def get_hblock_block_size(self):
		self.seek(0x428)
		return self.readInt32()

	def get_hblock_uk1(self):
		self.seek(0x42C)
		return self.read(0x04)			

	def get_htable_offset(self):
		self.seek(0x430)
		return self.readInt64()	
		
	def get_htable_size(self):
		self.seek(0x438)
		return self.readInt64()				
	
	def get_pfs0_offset(self):
		self.seek(0x440)
		return self.readInt64()			
		
	def get_pfs0_size(self):
		self.seek(0x448)
		return self.readInt64()			


class Nca(File):
	def __init__(self, path = None, mode = 'rb', cryptoType = -1, cryptoKey = -1, cryptoCounter = -1):
		self.header = None
		self.sectionFilesystems = []
		super(Nca, self).__init__(path, mode, cryptoType, cryptoKey, cryptoCounter)
			
	def __iter__(self):
		return self.sectionFilesystems.__iter__()
		
	def __getitem__(self, key):
		return self.sectionFilesystems[key]

	def open(self, file = None, mode = 'rb', cryptoType = -1, cryptoKey = -1, cryptoCounter = -1):

		super(Nca, self).open(file, mode, cryptoType, cryptoKey, cryptoCounter)

		self.header = NcaHeader()
		self.partition(0x0, 0xC00, self.header, Fs.Type.Crypto.XTS, uhx(Keys.get('header_key')))
		#Print.info('partition complete, seeking')
		
		self.header.seek(0x400)
		#Print.info('reading')
		#Hex.dump(self.header.read(0x200))
		#exit()

		for i in range(4):
			fs = GetSectionFilesystem(self.header.read(0x200), cryptoKey = self.header.titleKeyDec)
			#Print.info('fs type = ' + hex(fs.fsType))
			#Print.info('fs crypto = ' + hex(fs.cryptoType))
			#Print.info('st end offset = ' + str(self.header.sectionTables[i].endOffset - self.header.sectionTables[i].offset))
			#Print.info('fs offset = ' + hex(self.header.sectionTables[i].offset))
			#Print.info('fs section start = ' + hex(fs.sectionStart))
			#Print.info('titleKey = ' + str(hx(self.header.titleKeyDec)))
			try:
				self.partition(self.header.sectionTables[i].offset + fs.sectionStart, self.header.sectionTables[i].endOffset - self.header.sectionTables[i].offset, fs, cryptoKey = self.header.titleKeyDec)
			except BaseException as e:
				pass
				#Print.info(e)
				#raise

			if fs.fsType:
				self.sectionFilesystems.append(fs)
		
		
		self.titleKeyDec = None
		self.masterKey = None

	def get_hblock(self):		
		version = self.header.get_hblock_version()
		Print.info('version: ' + str(int.from_bytes(version, byteorder='little')))
		filesystem = self.header.get_hblock_filesystem()
		Print.info('filesystem: ' + str(int.from_bytes(filesystem, byteorder='little')))
		hash_type = self.header.get_hblock_hash_type()
		Print.info('hash type: ' + str(int.from_bytes(hash_type, byteorder='little')))
		crypto_type = self.header.get_hblock_crypto_type()
		Print.info('crypto type: ' + str(int.from_bytes(crypto_type, byteorder='little')))
		hash_from_htable = self.header.get_htable_hash()
		Print.info('hash from hash table: ' + str(hx(hash_from_htable)))
		block_size = self.header.get_hblock_block_size()
		Print.info('block size in bytes: ' + str(hx(block_size.to_bytes(8, byteorder='big'))))
		v_unkn1 = self.header.get_hblock_uk1()
		htable_offset = self.header.get_htable_offset()
		Print.info('hash table offset: ' +  str(hx(htable_offset.to_bytes(8, byteorder='big'))))
		htable_size = self.header.get_htable_size()
		Print.info('Size of hash-table: ' +  str(hx(htable_size.to_bytes(8, byteorder='big'))))			
		pfs0_offset = self.header.get_pfs0_offset()
		Print.info('Pfs0 offset: ' +  str(hx(pfs0_offset.to_bytes(8, byteorder='big'))))	
		pfs0_size = self.header.get_pfs0_size()
		Print.info('Pfs0 size: ' +  str(hx(pfs0_size.to_bytes(8, byteorder='big'))))	
			
		
	def get_pfs0_hash_data(self):	
		block_size = self.header.get_hblock_block_size()
		#Print.info('block size in bytes: ' + str(hx(block_size.to_bytes(8, byteorder='big'))))
		pfs0_size = self.header.get_pfs0_size()
		#Print.info('Pfs0 size: ' +  str(hx(pfs0_size.to_bytes(8, byteorder='big'))))
		multiplier=pfs0_size/block_size
		multiplier=math.ceil(multiplier)
		#Print.info('Multiplier: ' +  str(multiplier))
		return pfs0_size,block_size,multiplier
		
	def pfs0_MULT(self):	
		block_size = self.header.get_hblock_block_size()
		#Print.info('block size in bytes: ' + str(hx(block_size.to_bytes(8, byteorder='big'))))
		pfs0_size = self.header.get_pfs0_size()
		#Print.info('Pfs0 size: ' +  str(hx(pfs0_size.to_bytes(8, byteorder='big'))))
		multiplier=pfs0_size/block_size
		multiplier=math.ceil(multiplier)
		#Print.info('Multiplier: ' +  str(multiplier))
		return multiplier		
	
	def get_pfs0_hash(self, file = None, mode = 'rb', cryptoType = -1, cryptoKey = -1, cryptoCounter = -1):		
		mult=self.pfs0_MULT()
		for f in self:
			cryptoType=f.get_cryptoType()
			cryptoKey=f.get_cryptoKey()	
			cryptoCounter=f.get_cryptoCounter()
		super(Nca, self).open(file, mode, cryptoType, cryptoKey, cryptoCounter)
		self.seek(0xC00+self.header.get_htable_offset())
		hash_from_pfs0=self.read(0x20*mult)
		return hash_from_pfs0
		
	def calc_htable_hash(self):		
		indent = 2
		tabs = '\t' * indent
		htable = self.get_pfs0_hash()
		sha=sha256(htable).hexdigest()		
		sha_hash= bytes.fromhex(sha)
		Print.info(tabs + 'calculated table hash: ' + str(hx(sha_hash)))
		return sha_hash		

	def calc_pfs0_hash(self, file = None, mode = 'rb'):	
		mult=self.pfs0_MULT()
		indent = 2
		tabs = '\t' * indent
		for f in self:
			cryptoType2=f.get_cryptoType()
			cryptoKey2=f.get_cryptoKey()	
			cryptoCounter2=f.get_cryptoCounter()
		super(Nca, self).open(file, mode, cryptoType2, cryptoKey2, cryptoCounter2)
		pfs0_offset = self.header.get_pfs0_offset()
		pfs0_size = self.header.get_pfs0_size()
		block_size = self.header.get_hblock_block_size()
		self.seek(0xC00+self.header.get_htable_offset()+pfs0_offset)
		if mult>1:
			pfs0=self.read(block_size)
		else:
			pfs0=self.read(pfs0_size)
		sha=sha256(pfs0).hexdigest()
		#Print.info('caculated hash from pfs0: ' + sha)	
		sha_signature = bytes.fromhex(sha)
		Print.info(tabs + 'calculated hash from pfs0: ' + str(hx(sha_signature)))
		return sha_signature
		
	def set_pfs0_hash(self,value):
		file = None	
		mode = 'r+b'
		for f in self:
			cryptoType2=f.get_cryptoType()
			cryptoKey2=f.get_cryptoKey()	
			cryptoCounter2=f.get_cryptoCounter()
		super(Nca, self).open(file, mode, cryptoType2, cryptoKey2, cryptoCounter2)
		self.seek(0xC00+self.header.get_htable_offset())
		self.write(value)		
	
	def get_req_system(self, file = None, mode = 'rb'):	
		indent = 1
		tabs = '\t' * indent
		for f in self:
			cryptoType=f.get_cryptoType()
			cryptoKey=f.get_cryptoKey()	
			cryptoCounter=f.get_cryptoCounter()		
		pfs0_offset=0xC00+self.header.get_htable_offset()+self.header.get_pfs0_offset()
		super(Nca, self).open(file, mode, cryptoType, cryptoKey, cryptoCounter)
		self.seek(pfs0_offset+0x8)
		pfs0_table_size=self.readInt32()
		cmt_offset=pfs0_offset+0x28+pfs0_table_size
		self.seek(cmt_offset+0x28)		
		min_sversion=self.readInt32()
		Print.info(tabs + 'RequiredSystemVersion = ' + str(min_sversion))
		return min_sversion		

	def write_req_system(self, verNumber):
		indent = 1
		tabs = '\t' * indent
		file = None
		mode = 'r+b'	
		for f in self:
			cryptoType=f.get_cryptoType()
			cryptoKey=f.get_cryptoKey()	
			cryptoCounter=f.get_cryptoCounter()
		pfs0_offset=0xC00+self.header.get_htable_offset()+self.header.get_pfs0_offset()
		super(Nca, self).open(file, mode, cryptoType, cryptoKey, cryptoCounter)
		self.seek(pfs0_offset+0x8)
		pfs0_table_size=self.readInt32()
		cmt_offset=pfs0_offset+0x28+pfs0_table_size
		self.seek(cmt_offset+0x28)	
		min_sversion=self.readInt32()
		#Print.info('Original RequiredSystemVersion = ' + str(min_sversion))
		self.seek(cmt_offset+0x28)	
		self.writeInt64(verNumber)
		self.seek(cmt_offset+0x28)	
		min_sversion=self.readInt32()
		Print.info(tabs + 'New RequiredSystemVersion = ' + str(min_sversion))
		return min_sversion

	def write_version(self, verNumber):
		indent = 1
		tabs = '\t' * indent
		file = None
		mode = 'r+b'	
		for f in self:
			cryptoType=f.get_cryptoType()
			cryptoKey=f.get_cryptoKey()	
			cryptoCounter=f.get_cryptoCounter()
		pfs0_offset=0xC00+self.header.get_htable_offset()+self.header.get_pfs0_offset()
		super(Nca, self).open(file, mode, cryptoType, cryptoKey, cryptoCounter)
		self.seek(pfs0_offset+0x8)
		pfs0_table_size=self.readInt32()
		cmt_offset=pfs0_offset+0x28+pfs0_table_size
		self.seek(cmt_offset)
		titleid=self.readInt64()
		tnumber = verNumber.to_bytes(0x04, byteorder='little')
		titleversion = self.write(tnumber)
		self.seek(cmt_offset)
		titleid=self.readInt64()
		titleversion = self.read(0x4)
		Print.info('version = ' + str(int.from_bytes(titleversion, byteorder='little')))
		return titleversion			
		
	def removeTitleRightsnca(self, masterKeyRev, titleKeyDec):
		Print.info('titleKeyDec =\t' + str(hx(titleKeyDec)))
		Print.info('masterKeyRev =\t' + hex(masterKeyRev))
		Print.info('writing masterKeyRev for %s, %d' % (str(self._path),  masterKeyRev))
		crypto = aes128.AESECB(Keys.keyAreaKey(Keys.getMasterKeyIndex(masterKeyRev), self.header.keyIndex))
		encKeyBlock = crypto.encrypt(titleKeyDec * 4)
		self.header.setRightsId(0)
		self.header.setKeyBlock(encKeyBlock)
		Hex.dump(encKeyBlock)		
		
	def printtitleId(self, indent = 0):	
		Print.info(str(self.header.titleId))
		
	def print_nca_type(self, indent = 0):	
		Print.info(str(self.header.contentType))
			
	def cardstate(self, indent = 0):	
		Print.info(hex(self.header.isGameCard))
		
	def read_pfs0_header(self, file = None, mode = 'rb'):
		for f in self:
			cryptoType=f.get_cryptoType()
			cryptoKey=f.get_cryptoKey()	
			cryptoCounter=f.get_cryptoCounter()		
		pfs0_offset=0xC00+self.header.get_htable_offset()+self.header.get_pfs0_offset()
		super(Nca, self).open(file, mode, cryptoType, cryptoKey, cryptoCounter)
		self.seek(pfs0_offset)
		pfs0_magic = self.read(4)
		pfs0_nfiles=self.readInt32()
		pfs0_table_size=self.readInt32()
		pfs0_reserved=self.read(0x4)
		Print.info('PFS0 Magic = ' + str(pfs0_magic))
		Print.info('PFS0 number of files = ' + str(pfs0_nfiles))
		Print.info('PFS0 string table size = ' + str(hx(pfs0_table_size.to_bytes(4, byteorder='big'))))
		for i in range(pfs0_nfiles):
			Print.info('........................')							
			Print.info('PFS0 Content number ' + str(i+1))
			Print.info('........................')
			f_offset = self.readInt64()
			Print.info('offset = ' + str(hx(f_offset.to_bytes(8, byteorder='big'))))
			f_size = self.readInt32()
			Print.info('Size =\t' +  str(hx(pfs0_table_size.to_bytes(4, byteorder='big'))))
			filename_offset = self.readInt32()
			Print.info('offset of filename = ' + str(hx(f_offset.to_bytes(8, byteorder='big'))))
			f_reserved= self.read(0x4)

	def read_cnmt(self, file = None, mode = 'rb'):
		for f in self:
			cryptoType=f.get_cryptoType()
			cryptoKey=f.get_cryptoKey()	
			cryptoCounter=f.get_cryptoCounter()
		pfs0_offset=0xC00+self.header.get_htable_offset()+self.header.get_pfs0_offset()
		super(Nca, self).open(file, mode, cryptoType, cryptoKey, cryptoCounter)
		self.seek(pfs0_offset+0x8)
		pfs0_table_size=self.readInt32()
		cmt_offset=pfs0_offset+0x28+pfs0_table_size
		self.seek(cmt_offset)
		titleid=self.readInt64()
		titleversion = self.read(0x4)
		self.seek(cmt_offset+0xE)
		offset=self.readInt16()
		content_entries=self.readInt16()
		meta_entries=self.readInt16()
		self.seek(cmt_offset+0x20)
		original_ID=self.readInt64()
		self.seek(cmt_offset+0x28)					
		min_sversion=self.readInt32()
		end_of_emeta=self.readInt32()		
		Print.info('')	
		Print.info('...........................................')								
		Print.info('Reading: ' + str(self._path))
		Print.info('...........................................')							
		Print.info('titleid = ' + str(hx(titleid.to_bytes(8, byteorder='big'))))
		Print.info('version = ' + str(int.from_bytes(titleversion, byteorder='little')))
		Print.info('Table offset = '+ str(hx((offset+0x20).to_bytes(2, byteorder='big'))))
		Print.info('number of content = '+ str(content_entries))
		Print.info('number of meta entries = '+ str(meta_entries))
		Print.info('Application id\Patch id = ' + str(hx(original_ID.to_bytes(8, byteorder='big'))))
		Print.info('RequiredVersion = ' + str(min_sversion))
		self.seek(cmt_offset+offset+0x20)
		for i in range(content_entries):
			Print.info('........................')							
			Print.info('Content number ' + str(i+1))
			Print.info('........................')
			vhash = self.read(0x20)
			Print.info('hash =\t' + str(hx(vhash)))
			NcaId = self.read(0x10)
			Print.info('NcaId =\t' + str(hx(NcaId)))
			size = self.read(0x6)
			Print.info('Size =\t' + str(int.from_bytes(size, byteorder='little', signed=True)))
			ncatype = self.read(0x1)
			Print.info('ncatype = ' + str(int.from_bytes(ncatype, byteorder='little', signed=True)))
			unknown = self.read(0x1)									
	
	def printInfo(self, indent = 0):
		tabs = '\t' * indent
		Print.info('\n%sNCA Archive\n' % (tabs))
		super(Nca, self).printInfo(indent)
#		Print.info(tabs + 'Header Block Hash: ' + str(hx(self.header.get_hblock_hash())))
#		self.header.calculate_hblock_hash()
#		self.get_hblock()
#		self.calc_htable_hash()
#		Print.info('hash from pfs0: ' + str(hx(self.get_pfs0_hash())))
#		self.calc_pfs0_hash()
#		self.get_req_system()
#		Print.info(tabs + 'RSA-2048 signature 1 = ' + str(hx(self.header.signature1)))
#		Print.info(tabs + 'RSA-2048 signature 2 = ' + str(hx(self.header.signature2)))
		Print.info(tabs + 'magic = ' + str(self.header.magic))
		Print.info(tabs + 'titleId = ' + str(self.header.titleId))
		Print.info(tabs + 'rightsId = ' + str(self.header.rightsId))
		Print.info(tabs + 'isGameCard = ' + hex(self.header.isGameCard))
		Print.info(tabs + 'contentType = ' + str(self.header.contentType))
		#Print.info(tabs + 'cryptoType = ' + str(self.header.getCryptoType()))
		Print.info(tabs + 'SDK version = ' + str(self.header.sdkVersion))
		Print.info(tabs + 'Size: ' + str(self.header.size))
		Print.info(tabs + 'Crypto-Type1: ' + str(self.header.cryptoType))
		Print.info(tabs + 'Crypto-Type2: ' + str(self.header.cryptoType2))
		Print.info(tabs + 'key Index: ' + str(self.header.keyIndex))
		#Print.info(tabs + 'key Block: ' + str(self.header.getKeyBlock()))
		for key in self.header.keys:
			Print.info(tabs + 'key Block: ' + str(hx(key)))
		
		Print.info('\n%sPartitions:' % (tabs))
		
		for s in self:
			s.printInfo(indent+1)
			
		#self.read_pfs0_header()	
		#self.read_cnmt()
			
