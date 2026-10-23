import os
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Integer, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker
Base=declarative_base()
class Version(Base):
    __tablename__='versions'
    id=Column(String,primary_key=True)
    sequence=Column(Integer,unique=True,nullable=False)
    file_hash=Column(String,nullable=False)
    warnings=Column(JSON,nullable=False)
class Node(Base):
    __tablename__='nodes'
    id=Column(String,primary_key=True)
    version=Column(String,ForeignKey('versions.id'),nullable=False,index=True)
    key=Column(String,nullable=False)
    data=Column(JSON,nullable=False)
    __table_args__=(UniqueConstraint('version','key'),)
class Selection(Base):
    __tablename__='selections'
    id=Column(String,primary_key=True)
    name=Column(String,unique=True,nullable=False)
    version=Column(String,ForeignKey('versions.id'),nullable=False)
    nodes=Column(JSON,nullable=False)
class Generation(Base):
    __tablename__='generations'
    id=Column(String,primary_key=True)
    selection_id=Column(String,ForeignKey('selections.id'),nullable=False,index=True)
    document=Column(JSON,nullable=False)
def database(url=None):
    Path('runtime').mkdir(exist_ok=True)
    engine=create_engine(url or os.getenv('DATABASE_URL','sqlite:///runtime/ct200.db'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    return sessionmaker(engine,expire_on_commit=False)
