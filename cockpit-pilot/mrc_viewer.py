import mrcfile
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backend_bases import NavigationToolbar2
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5 import NavigationToolbar2QT as NavigationToolbar
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QPushButton, QWidget

class ImageNavigator(QMainWindow):
    def __init__(self, data, header):
        super().__init__()
        self.data = data
        self.header = header
        self.num_images = data.shape[0] if data.ndim > 2 else 1
        self.current_index = 0

        self.initUI()

    def initUI(self):
        self.setWindowTitle('MRC Image Viewer')

        self.canvas = FigureCanvas(plt.Figure())
        self.ax = self.canvas.figure.subplots()
        self.image_display = self.ax.imshow(self.data[self.current_index, :, :], cmap='gray')
        self.ax.set_title(f"Image {self.current_index + 1}")
        self.ax.axis('off')

        self.toolbar = NavigationToolbar(self.canvas, self)
        self.addToolBar(self.toolbar)

        self.prev_button = QPushButton('Previous', self)
        self.prev_button.clicked.connect(self.prev_image)
        self.toolbar.addWidget(self.prev_button)

        self.next_button = QPushButton('Next', self)
        self.next_button.clicked.connect(self.next_image)
        self.toolbar.addWidget(self.next_button)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(self.canvas)
        self.setCentralWidget(widget)

        self.update_display()
        self.show()

    def update_display(self):
        self.image_display.set_data(self.data[self.current_index, :, :])
        self.ax.set_title(f"Image {self.current_index + 1}")
        print(f"Displaying Image {self.current_index + 1}")
        self.print_metadata(self.current_index)
        self.canvas.draw()

    def prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.update_display()

    def next_image(self):
        if self.current_index < self.num_images - 1:
            self.current_index += 1
            self.update_display()

    def print_metadata(self, index):
        print("\nMetadata for current image:")
        print(f"Number of columns: {self.header.nx}")
        print(f"Number of rows: {self.header.ny}")
        print(f"Number of sections: {self.header.nz}")
        print(f"Pixel spacing (angstroms): {self.header.cella}")
        print(f"Map mode: {self.header.mode}")
        print(f"Start point of sub-volume (x, y, z): ({self.header.nxstart}, {self.header.nystart}, {self.header.nzstart})")
        print(f"Number of intervals along x, y, z: ({self.header.mx}, {self.header.my}, {self.header.mz})")
        print(f"Min, Max, Mean density: {self.header.dmin}, {self.header.dmax}, {self.header.dmean}")
        print(f"Is this a volumetric map? {'Yes' if self.header.ispg == 0 else 'No'}")
        if hasattr(self.header, 'next'):
            print(f"Number of bytes in extended header: {self.header.next}")
        else:
            print("Number of bytes in extended header: Not available")
        if hasattr(self.header, 'imodStamp'):
            print(f"Image type (0=image, 1=diffraction): {self.header.imodStamp}")
        else:
            print("Image type (0=image, 1=diffraction): Not available")

        # Displaying metadata for previous and next images
        if index > 0:
            print("\nMetadata for previous image:")
            self.print_basic_metadata(index - 1)
        if index < self.num_images - 1:
            print("\nMetadata for next image:")
            self.print_basic_metadata(index + 1)

    def print_basic_metadata(self, index):
        print(f"Image {index + 1}:")
        print(f"Min, Max density: {np.min(self.data[index])}, {np.max(self.data[index])}")

def display_images_from_mrc(file_path):
    try:
        with mrcfile.open(file_path, permissive=True) as mrc:
            # Read the image data and header
            data = mrc.data
            header = mrc.header

            # Determine the number of images in the stack
            num_images = data.shape[0] if data.ndim > 2 else 1

            print(f"\nNumber of images in the stack: {num_images}")

            # Display images with navigation and metadata
            app = QApplication([])
            navigator = ImageNavigator(data, header)
            app.exec_()

    except Exception as e:
        print(f"An error occurred: {e}")

# Example usage:
file_path = r'C:\MUI_DATA\boris\20240711-234218'
display_images_from_mrc(file_path)
