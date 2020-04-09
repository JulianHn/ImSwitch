# -*- coding: utf-8 -*-
"""
Created on Wed Apr  8 19:11:50 2020

@author: andreas.boden
"""
import SignalDesigner

class ValidChildFactory():
    def __new__(cls, className, *args, **kwargs):
        product = eval(className+'()')
        if product.isValidChild(*args, **kwargs):
            return product