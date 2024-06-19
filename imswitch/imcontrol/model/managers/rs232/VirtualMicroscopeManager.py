from imswitch.imcommon.model import initLogger
from imswitch.imcommon.model import APIExport
try:
    import NanoImagingPack as nip
    IS_NIP = True
except:
    IS_NIP = False
import numpy as np
import matplotlib.pyplot as plt 
import threading
import time
import numpy as np
import cv2
import threading
import time
import numpy as np
import imswitch
import os

class VirtualMicroscopeManager:
    """ A low-level wrapper for TCP-IP communication (ESP32 REST API)
    """

    def __init__(self, rs232Info, name, **_lowLevelManagers):
        self.__logger = initLogger(self, instanceName=name)
        self._settings = rs232Info.managerProperties
        self._name = name
        try:
            self._imagePath = rs232Info.managerProperties['imagePath']
        except:
            package_dir = os.path.dirname(os.path.abspath(imswitch.__file__))
            self._imagePath = os.path.join(package_dir, "_data/images/histoASHLARStitch.jpg")
            
        self._virtualMicroscope = VirtualMicroscopy(self._imagePath)
        self._positioner = self._virtualMicroscope.positioner
        self._camera = self._virtualMicroscope.camera
        self._illuminator = self._virtualMicroscope.illuminator
        

        '''
        # Test the functionality
        for i in range(10):
            microscope.positioner.move(x=5, y=5)
            microscope.illuminator.set_intensity(intensity=1.5)
            frame = microscope.get_frame()
            cv2.imshow("Microscope View", frame)
            cv2.waitKey(100)

        cv2.destroyAllWindows()
        '''

    def finalize(self):
        self._virtualMicroscope.stop()
    
    


class Camera:
    def __init__(self, parent, filePath="path_to_image.jpeg"):
        self._parent = parent
        self.image = np.mean(cv2.imread(filePath), axis=2)
        
        self.image /= np.max(self.image)
        self.lock = threading.Lock()
        self.SensorWidth = 512 #self.image.shape[1]
        self.SensorHeight = 512 #self.image.shape[0]
        self.model = "VirtualCamera"
        self.PixelSize = 1.0
        self.isRGB = False
        self.frameNumber = 0
        # precompute noise so that we will save energy and trees
        self.noiseStack = np.random.randn(self.SensorHeight,self.SensorWidth,100)*2
        
    def produce_frame(self, x_offset=0, y_offset=0, light_intensity=1.0, defocusPSF=None):
        """Generate a frame based on the current settings."""
        with self.lock:
            # add moise
            image = self.image.copy()
            # Adjust image based on offsets
            image = np.roll(np.roll(image, int(x_offset), axis=1), int(y_offset), axis=0)
            image = nip.extract(image, (self.SensorWidth, self.SensorHeight))

            # do all post-processing on cropped image
            if IS_NIP and defocusPSF is not None and not defocusPSF.shape == ():
                print("Defocus:"+str(defocusPSF.shape))
                image = np.array(np.real(nip.convolve(image, defocusPSF)))
            image = np.float32(image)/np.max(image) * np.float32(light_intensity)
            image += self.noiseStack[:,:,np.random.randint(0,100)]
                        
            # Adjust illumination
            image = image.astype(np.uint16)
            time.sleep(0.1)
            return np.array(image)
        
    def getLast(self, returnFrameNumber=False):
        position = self._parent.positioner.get_position()
        defocusPSF = np.squeeze(self._parent.positioner.get_psf())
        intensity = self._parent.illuminator.get_intensity(1)
        self.frameNumber += 1
        if returnFrameNumber:
            return self.produce_frame(x_offset=position['X'], y_offset=position['Y'], light_intensity=intensity, defocusPSF=defocusPSF), self.frameNumber
        else:
            return self.produce_frame(x_offset=position['X'], y_offset=position['Y'], light_intensity=intensity, defocusPSF=defocusPSF)
    

    def setPropertyValue(self, propertyName, propertyValue):
        pass
    
class Positioner:
    def __init__(self, parent):
        self._parent = parent
        self.position = {'X': 0, 'Y': 0, 'Z': 0, 'A': 0}
        self.mDimensions = (self._parent.camera.SensorWidth, self._parent.camera.SensorHeight)
        self.lock = threading.Lock()
        if IS_NIP:
            self.psf = self.compute_psf(dz=0)
        else: 
            self.psf = None

    def move(self, x=None, y=None, z=None, a=None, is_absolute=False):
        with self.lock:
            if is_absolute:
                if x is not None:
                    self.position['X'] = x
                if y is not None:
                    self.position['Y'] = y
                if z is not None:
                    self.position['Z'] = z
                    self.compute_psf(self.position['Z'])
                if a is not None:
                    self.position['A'] = a
            else:
                if x is not None:
                    self.position['X'] += x
                if y is not None:
                    self.position['Y'] += y
                if z is not None:
                    self.position['Z'] += z
                    self.compute_psf(self.position['Z'])
                if a is not None:                    
                    self.position['A'] += a

    def get_position(self):
        with self.lock:
            return self.position.copy()

    def compute_psf(self, dz):
        dz = np.float32(dz)
        print("Defocus:"+str(dz))
        if IS_NIP and dz != 0:
            obj = nip.image(np.zeros(self.mDimensions))
            obj.pixelsize = (100., 100.)
            paraAbber = nip.PSF_PARAMS()
            #aber_map = nip.xx(obj.shape[-2:]).normalize(1)
            paraAbber.aberration_types = [paraAbber.aberration_zernikes.spheric]
            paraAbber.aberration_strength = [np.float32(dz)/10]
            psf = nip.psf(obj, paraAbber)
            self.psf = psf.copy()
            del psf
            del obj
        else:
            self.psf = None

        
    def get_psf(self):
        return self.psf
        


class Illuminator:
    def __init__(self, parent):
        self._parent = parent
        self.intensity = 0
        self.lock = threading.Lock()

    def set_intensity(self, channel=1, intensity=0):
        with self.lock:
            self.intensity = intensity

    def get_intensity(self, channel):
        with self.lock:
            return self.intensity
        
        

class VirtualMicroscopy:
    def __init__(self, filePath="path_to_image.jpeg"):
        self.camera = Camera(self, filePath)
        self.positioner = Positioner(self)
        self.illuminator = Illuminator(self)
        
    def stop(self):
        pass


if __name__ == "__main__":
    import matplotlib.pyplot as plt
    # Read the image locally
    mFWD = os.path.dirname(os.path.realpath(__file__)).split("imswitch")[0]
    imagePath = mFWD+"imswitch/_data/images/histoASHLARStitch.jpg"
    microscope = VirtualMicroscopy(filePath=imagePath)
    microscope.illuminator.set_intensity(intensity=1000)
        
    for i in range(10):
        microscope.positioner.move(x=i, y=i, z=i, is_absolute=True)
        frame = microscope.camera.getLast()
        plt.imsave(f"frame_{i}.png", frame)
    cv2.destroyAllWindows()

# Copyright (C) 2020-2023 ImSwitch developers
# This file is part of ImSwitch.
#
# ImSwitch is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ImSwitch is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
