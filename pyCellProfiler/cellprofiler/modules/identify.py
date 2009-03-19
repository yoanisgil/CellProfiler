"""identify.py - a base class for common functionality for identify modules

CellProfiler is distributed under the GNU General Public License.
See the accompanying file LICENSE for details.

Developed by the Broad Institute
Copyright 2003-2009

Please see the AUTHORS file for credits.

Website: http://www.cellprofiler.org
"""

__version__="$Revision$"

import math
import scipy.ndimage
import scipy.sparse
import numpy
import scipy.stats

import cellprofiler.cpmodule
import cellprofiler.settings as cps
from cellprofiler.cpmath.otsu import otsu
import cellprofiler.cpmath.outline
import cellprofiler.objects
from cellprofiler.cpmath.smooth import smooth_with_noise

TM_OTSU                         = "Otsu"
TM_OTSU_GLOBAL                  = "Otsu Global"
TM_OTSU_ADAPTIVE                = "Otsu Adaptive"
TM_OTSU_PER_OBJECT              = "Otsu PerObject"
TM_MOG                          = "MoG"
TM_MOG_GLOBAL                   = "MoG Global"
TM_MOG_ADAPTIVE                 = "MoG Adaptive"
TM_MOG_PER_OBJECT               = "MoG PerObject"
TM_BACKGROUND                   = "Background"
TM_BACKGROUND_GLOBAL            = "Background Global"
TM_BACKGROUND_ADAPTIVE          = "Background Adaptive"
TM_BACKGROUND_PER_OBJECT        = "Background PerObject"
TM_ROBUST_BACKGROUND            = "RobustBackground"
TM_ROBUST_BACKGROUND_GLOBAL     = "RobustBackground Global"
TM_ROBUST_BACKGROUND_ADAPTIVE   = "RobustBackground Adaptive"
TM_ROBUST_BACKGROUND_PER_OBJECT = "RobustBackground PerObject"
TM_RIDLER_CALVARD               = "RidlerCalvard"
TM_RIDLER_CALVARD_GLOBAL        = "RidlerCalvard Global"
TM_RIDLER_CALVARD_ADAPTIVE      = "RidlerCalvard Adaptive"
TM_RIDLER_CALVARD_PER_OBJECT    = "RidlerCalvard PerObject"
TM_KAPUR                        = "Kapur"
TM_KAPUR_GLOBAL                 = "Kapur Global"
TM_KAPUR_ADAPTIVE               = "Kapur Adaptive"
TM_KAPUR_PER_OBJECT             = "Kapur PerObject"
TM_ALL                          = "All"
TM_SET_INTERACTIVELY            = "Set interactively"
TM_MANUAL                       = "Manual"
TM_BINARY_IMAGE                 = "Binary image"
TM_GLOBAL                       = "Global"
TM_ADAPTIVE                     = "Adaptive"
TM_PER_OBJECT                   = "PerObject"

class Identify(cellprofiler.cpmodule.CPModule):
    def get_threshold(self, image, mask, objects):
        """Compute the threshold using whichever algorithm was selected by the user
        image - image to threshold
        mask  - ignore pixels whose mask value is false
        objects - labels that restrict thresholding to within the object boundary
        returns: threshold to use (possibly an array) and global threshold
        """
        if self.threshold_method == TM_MANUAL:
            return self.manual_threshold.value, self.manual_threshold.value
        global_threshold = self.get_global_threshold(image, mask)
        if self.threshold_modifier == TM_GLOBAL:
            local_threshold=global_threshold
        elif self.threshold_modifier == TM_ADAPTIVE:
            local_threshold = self.get_adaptive_threshold(image, mask, global_threshold)
        elif self.threshold_modifier == TM_PER_OBJECT:
            local_threshold = self.get_per_object_threshold(image, mask, objects, global_threshold)
        else:
            raise NotImplementedError("%s thresholding is not implemented"%(self.threshold_modifier))
        if isinstance(local_threshold, numpy.ndarray):
            local_threshold[local_threshold < self.threshold_range.min] =\
                self.threshold_range.min
            local_threshold[local_threshold > self.threshold_range.max] =\
                self.threshold_range.max
        else:
            local_threshold = max(local_threshold,self.threshold_range.min)
            local_threshold = min(local_threshold,self.threshold_range.max)
        local_threshold = local_threshold * self.threshold_correction_factor.value
        return local_threshold, global_threshold
    
    def get_global_threshold(self,image,mask):
        """Compute a single threshold over the whole image"""
        if self.threshold_algorithm == TM_OTSU:
            return otsu(image[mask],
                        self.threshold_range.min,
                        self.threshold_range.max)
        elif self.threshold_algorithm == TM_MOG:
            return self.get_mog_threshold(image,mask)
        elif self.threshold_algorithm == TM_BACKGROUND:
            return self.get_background_threshold(image,mask)
        elif self.threshold_algorithm == TM_ROBUST_BACKGROUND:
            return self.get_robust_background_threshold(image,mask)
        elif self.threshold_algorithm == TM_RIDLER_CALVARD:
            return self.get_ridler_calvard_threshold(image, mask)
        elif self.threshold_algorithm == TM_KAPUR:
            return self.get_kapur_threshold(image,mask)
        else:
            raise NotImplementedError("%s algorithm not implemented"%(self.threshold_algorithm.value))
    
    def get_adaptive_threshold(self,image,mask,threshold):
        """Given a global threshold, compute a threshold per pixel
        
        Break the image into blocks, computing the threshold per block.
        Afterwards, constrain the block threshold to .7 T < t < 1.5 T.
        
        Block sizes must be at least 50x50. Images > 500 x 500 get 10x10
        blocks.
        """
        # Compute the minimum and maximum allowable thresholds
        min_threshold = max(.7 * threshold,0)
        max_threshold = min(1.5 * threshold,1)
        
        # for the X and Y direction, find the # of blocks, given the
        # size constraints
        image_size = numpy.array(image.shape[:2],dtype=int)
        block_size = image_size / 10
        block_size[block_size<50] = 50
        nblocks = image_size / block_size
        #
        # Use a floating point block size to apportion the roundoff
        # roughly equally to each block
        #
        increment = ( numpy.array(image_size,dtype=float) / 
                      numpy.array(nblocks,dtype=float))
        #
        # Put the answer here
        #
        thresh_out = numpy.zeros(image_size, image.dtype)
        #
        # Loop once per block, computing the "global" threshold within the
        # block.
        #
        for i in range(nblocks[0]):
            i0 = int(i*increment[0])
            i1 = int((i+1)*increment[0])
            for j in range(nblocks[1]):
                j0 = int(j*increment[1])
                j1 = int((j+1)*increment[1])
                block = image[i0:i1,j0:j1]
                block_mask = mask[i0:i1,j0:j1]
                block_threshold = self.get_global_threshold(block, block_mask)
                block_threshold = max(block_threshold, min_threshold)
                block_threshold = min(block_threshold, max_threshold)
                thresh_out[i0:i1,j0:j1] = block_threshold
        return thresh_out
    
    def get_per_object_threshold(self,image,mask,objects,threshold):
        """Return a matrix giving threshold per pixel calculated per-object
        
        image - image to be thresholded
        mask  - mask out "don't care" pixels
        objects - a label mask indicating object boundaries
        threshold - the global threshold
        """
        labels = objects.segmented
        label_extents = scipy.ndimage.find_objects(labels,numpy.max(labels))
        local_threshold = numpy.ones(image.shape,image.dtype)
        for i,extent in zip(range(1,len(label_extents)+1),label_extents):
            label_mask = numpy.logical_and(mask[extent],labels[extent]==i)
            values = image[extent]
            per_object_threshold = self.get_global_threshold(values, label_mask)
            local_threshold[extent][label_mask] = per_object_threshold
        return local_threshold
    
    def get_mog_threshold(self,image,mask):
        """Compute a background using a mixture of gaussians
        
        This function finds a suitable
        threshold for the input image Block. It assumes that the pixels in the
        image belong to either a background class or an object class. 'pObject'
        is an initial guess of the prior probability of an object pixel, or
        equivalently, the fraction of the image that is covered by objects.
        Essentially, there are two steps. First, a number of Gaussian
        distributions are estimated to match the distribution of pixel
        intensities in OrigImage. Currently 3 Gaussian distributions are
        fitted, one corresponding to a background class, one corresponding to
        an object class, and one distribution for an intermediate class. The
        distributions are fitted using the Expectation-Maximization (EM)
        algorithm, a procedure referred to as Mixture of Gaussians modeling.
        When the 3 Gaussian distributions have been fitted, it's decided
        whether the intermediate class models background pixels or object
        pixels based on the probability of an object pixel 'pObject' given by
        the user.        
        """
        cropped_image = image[mask]
        pixel_count = numpy.product(cropped_image.shape)
        max_count   = 512**2 # maximum # of pixels analyzed
        #
        # We need at least 3 pixels to keep from crashingbecause the highest 
        # and lowest are chopped out below.
        #
        object_fraction = float(self.object_fraction.value)
        background_fraction = 1.0-object_fraction
        if pixel_count < 3/min(object_fraction,background_fraction):
            return 1
        if numpy.max(cropped_image)==numpy.min(cropped_image):
            return cropped_image[0]
        number_of_classes = 3
        if pixel_count > max_count:
            numpy.random.seed(0)
            pixel_indices = numpy.random.permutation(pixel_count)[:max_count]
            cropped_image = cropped_image[pixel_indices]
        # Initialize mean and standard deviations of the three Gaussian
        # distributions by looking at the pixel intensities in the original
        # image and by considering the percentage of the image that is
        # covered by object pixels. Class 1 is the background class and Class
        # 3 is the object class. Class 2 is an intermediate class and we will
        # decide later if it encodes background or object pixels. Also, for
        # robustness the we remove 1% of the smallest and highest intensities
        # in case there are any quantization effects that have resulted in
        # unnaturally many 0:s or 1:s in the image.
        cropped_image.sort()
        one_percent = (numpy.product(cropped_image.shape) + 99)/100
        cropped_image=cropped_image[one_percent:-one_percent]
        pixel_count = numpy.product(cropped_image.shape)
        # Guess at the class means for the 3 classes: background,
        # in-between and object
        bg_pixel = cropped_image[round(pixel_count * background_fraction/2.0)]
        fg_pixel = cropped_image[round(pixel_count * (1-object_fraction/2))]
        class_mean = numpy.array([bg_pixel, (bg_pixel+fg_pixel)/2,fg_pixel])
        class_std = numpy.ones((3,)) * 0.15
        # Initialize prior probabilities of a pixel belonging to each class.
        # The intermediate class steals some probability from the background
        # and object classes.
        class_prob = numpy.array([3.0/4.0 * background_fraction ,
                                  1.0/4.0,
                                  3.0/4.0 * object_fraction])
        # Expectation-Maximization algorithm for fitting the three Gaussian
        # distributions/classes to the data. Note, the code below is general
        # and works for any number of classes. Iterate until parameters don't
        # change anymore.
        delta = 1
        class_count = numpy.prod(class_mean.shape)
        while delta > 0.001:
            old_class_mean = class_mean.copy()
            # Update probabilities of a pixel belonging to the background or
            # object1 or object2
            pixel_class_prob = numpy.ndarray((pixel_count,class_count))
            for k in range(class_count):
                norm = scipy.stats.norm(class_mean[k],class_std[k])
                pixel_class_prob[:,k] = class_prob[k] * norm.pdf(cropped_image)
            pixel_class_normalizer = numpy.sum(pixel_class_prob,1)+.000000000001
            for k in range(class_count):
                pixel_class_prob[:,k] = pixel_class_prob[:,k] / pixel_class_normalizer
                # Update parameters in Gaussian distributions
                class_prob[k] = numpy.mean(pixel_class_prob[:,k])
                class_mean[k] = (numpy.sum(pixel_class_prob[:,k] * cropped_image) /
                                 (class_prob[k] * pixel_count))
                class_std[k] = \
                    math.sqrt(numpy.sum(pixel_class_prob[:,k] * 
                                        (cropped_image-class_mean[k])**2)/
                              (pixel_count * class_prob[k])) + .000001
            delta = numpy.sum(numpy.abs(old_class_mean - class_mean))
        # Now the Gaussian distributions are fitted and we can describe the
        # histogram of the pixel intensities as the sum of these Gaussian
        # distributions. To find a threshold we first have to decide if the
        # intermediate class 2 encodes background or object pixels. This is
        # done by choosing the combination of class probabilities "class_prob"
        # that best matches the user input "object_fraction".
        
        # Construct an equally spaced array of values between the background
        # and object mean
        ndivisions = 10000
        level = (numpy.array(range(ndivisions)) *
                 ((class_mean[2]-class_mean[0]) / ndivisions)
                 + class_mean[0])
        class_gaussian = numpy.ndarray((ndivisions,class_count))
        for k in range(class_count):
            norm = scipy.stats.norm(class_mean[k],class_std[k])
            class_gaussian[:,k] = class_prob[k] * norm.pdf(level)
        if (abs(class_prob[1]+class_prob[2]-object_fraction) <
            abs(class_prob[2]-object_fraction)):
            # classifying the intermediate as object more closely models
            # the user's desired object fraction
            background_distribution = class_gaussian[:,0]
            object_distribution = class_gaussian[:,1]+class_gaussian[:,2]
        else:
            background_distribution = class_gaussian[:,0]+class_gaussian[:,1]
            object_distribution = class_gaussian[:,2]
        # Now, find the threshold at the intersection of the background
        # distribution and the object distribution.
        index = numpy.argmin(numpy.abs(background_distribution-
                                       object_distribution))
        return level[index]

    def get_background_threshold(self,image,mask):
        """Get threshold based on the mode of the image
        The threshold is calculated by calculating the mode and multiplying by
        2 (an arbitrary empirical factor). The user will presumably adjust the
        multiplication factor as needed."""
        cropped_image = image[mask]
        if numpy.product(cropped_image.shape)==0:
            return 0
        if numpy.min(cropped_image) == numpy.max(cropped_image):
            return cropped_image[0]
        
        # Only do the histogram between values a bit removed from saturation
        robust_min = 0.02
        robust_max = 0.98
        nbins = 256
        cropped_image = cropped_image[numpy.logical_and(cropped_image > robust_min,
                                                        cropped_image < robust_max)]
        h = scipy.ndimage.histogram(cropped_image,0,1,nbins)
        index = numpy.argmax(h)
        cutoff = float(index) / float(nbins-1)
        return cutoff * 2

    def get_robust_background_threshold(self,image,mask):
        """Calculate threshold based on mean & standard deviation
           The threshold is calculated by trimming the top and bottom 5% of
           pixels off the image, then calculating the mean and standard deviation
           of the remaining image. The threshold is then set at 2 (empirical
           value) standard deviations above the mean.""" 

        cropped_image = image[mask]
        if numpy.product(cropped_image.shape)<3:
            return 0
        if numpy.min(cropped_image) == numpy.max(cropped_image):
            return cropped_image[0]
        
        cropped_image.sort()
        chop = int(round(numpy.product(cropped_image.shape) * .05))
        im   = cropped_image[chop:-chop]
        mean = im.mean()
        sd   = im.std()
        return mean+sd*2

    def get_ridler_calvard_threshold(self,image, mask):
        """Find a threshold using the method of Ridler and Calvard
        
        The reference for this method is:
        "Picture Thresholding Using an Iterative Selection Method" 
        by T. Ridler and S. Calvard, in IEEE Transactions on Systems, Man and
        Cybernetics, vol. 8, no. 8, August 1978.
        """
        cropped_image = image[mask]
        if numpy.product(cropped_image.shape)<3:
            return 0
        if numpy.min(cropped_image) == numpy.max(cropped_image):
            return cropped_image[0]
        
        # We want to limit the dynamic range of the image to 256. Otherwise,
        # an image with almost all values near zero can give a bad result.
        min_val = numpy.max(cropped_image)/256;
        cropped_image[cropped_image<min_val] = min_val;
        im = numpy.log(cropped_image);
        min_val = numpy.min(im);
        max_val = numpy.max(im);
        im = (im - min_val)/(max_val - min_val);
        pre_thresh = 0;
        # This method needs an initial value to start iterating. Using
        # graythresh (Otsu's method) is probably not the best, because the
        # Ridler Calvard threshold ends up being too close to this one and in
        # most cases has the same exact value.
        new_thresh = otsu(im)
        delta = 0.00001;
        while abs(pre_thresh - new_thresh)>delta:
            pre_thresh = new_thresh;
            mean1 = numpy.mean(im[im<pre_thresh]);
            mean2 = numpy.mean(im[im>=pre_thresh]);
            new_thresh = numpy.mean([mean1,mean2]);
        return math.exp(min_val + (max_val-min_val)*new_thresh);

    def get_kapur_threshold(self,image,mask):
        """The Kapur, Sahoo, & Wong method of thresholding, adapted to log-space."""
        cropped_image = image[mask]
        if numpy.product(cropped_image.shape)<3:
            return 0
        if numpy.min(cropped_image) == numpy.max(cropped_image):
            return cropped_image[0]
        log_image = numpy.log2(smooth_with_noise(cropped_image, 8))
        min_log_image = numpy.min(log_image)
        max_log_image = numpy.max(log_image)
        histogram = scipy.ndimage.histogram(log_image,
                                            min_log_image,
                                            max_log_image,
                                            256)
        histogram_values = (min_log_image + (max_log_image - min_log_image)*
                            numpy.array(range(256),float) / 255)
        # drop any zero bins
        keep = histogram != 0
        histogram = histogram[keep]
        histogram_values = histogram_values[keep]
        # check for corner cases
        if numpy.product(histogram_values)==1:
            return 2**histogram_values[0] 
        # Normalize to probabilities
        p = histogram.astype(float) / float(numpy.sum(histogram))
        # Find the probabilities totals up to and above each possible threshold.
        lo_sum = numpy.cumsum(p);
        hi_sum = lo_sum[-1] - lo_sum;
        lo_e = numpy.cumsum(p * numpy.log2(p));
        hi_e = lo_e[-1] - lo_e;

        # compute the entropies
        lo_entropy = lo_e / lo_sum - numpy.log2(lo_sum);
        hi_entropy = hi_e / hi_sum - numpy.log2(hi_sum);

        sum_entropy = lo_entropy[:-1] + hi_entropy[:-1];
        sum_entropy[numpy.logical_not(numpy.isfinite(sum_entropy))] = numpy.Inf
        entry = numpy.argmin(sum_entropy);
        return 2**((histogram_values[entry] + histogram_values[entry+1]) / 2);

    def get_threshold_modifier(self):
        """The threshold algorithm modifier
        
        TM_GLOBAL                       = "Global"
        TM_ADAPTIVE                     = "Adaptive"
        TM_PER_OBJECT                   = "PerObject"
        """
        parts = self.threshold_method.value.split(' ')
        return parts[1]
    
    threshold_modifier = property(get_threshold_modifier)
    
    def get_threshold_algorithm(self):
        """The thresholding algorithm, for instance TM_OTSU"""
        parts = self.threshold_method.value.split(' ')
        return parts[0]
    
    threshold_algorithm = property(get_threshold_algorithm)

def weighted_variance(image,mask,threshold):
    """Compute the log-transformed variance of foreground and background"""
    if not numpy.any(mask):
        return 0
    #
    # Clamp the dynamic range of the foreground
    #
    minval = numpy.max(image[mask])/256
    if minval == 0:
        return 0
    clamped_image = image[mask]
    clamped_image[clamped_image < minval] = minval
    
    if isinstance(threshold,numpy.ndarray):
        threshold = threshold[mask]
    fg = numpy.log2(clamped_image[clamped_image >=threshold])
    bg = numpy.log2(clamped_image[clamped_image < threshold])
    nfg = numpy.product(fg.shape)
    nbg = numpy.product(bg.shape)
    if nfg == 0:
        return numpy.var(bg)
    elif nbg == 0:
        return numpy.var(fg)
    else:
        return (numpy.var(fg) * nfg + numpy.var(bg)*nbg) / (nfg+nbg)

def sum_of_entropies(image, mask, threshold):
    """Bin the foreground and background pixels and compute the entropy 
    of the distribution of points among the bins
    """
    if not numpy.any(mask):
        return 0
    #
    # Clamp the dynamic range of the foreground
    #
    minval = numpy.max(image[mask])/256
    if minval == 0:
        return 0
    clamped_image = image.copy()
    clamped_image[clamped_image < minval] = minval
    #
    # Smooth image with -8 bits of noise
    #
    image = smooth_with_noise(clamped_image, 8)
    im_min = numpy.min(image)
    im_max = numpy.max(image)
    #
    # Figure out the bounds for the histogram
    #
    upper = math.log(im_max,2)
    lower = math.log(im_min,2)
    if upper == lower:
        # All values are the same, answer is log2 of # of pixels
        return math.log(numpy.sum(mask),2) 
    #
    # Create log-transformed lists of points in the foreground and background
    # 
    fg = image[numpy.logical_and(mask, image >= threshold)]
    bg = image[numpy.logical_and(mask, image < threshold)]
    log_fg = numpy.log2(fg)
    log_bg = numpy.log2(bg)
    #
    # Make these into histograms
    hfg = scipy.ndimage.histogram(log_fg,lower,upper,256)
    hbg = scipy.ndimage.histogram(log_bg,lower,upper,256)
    #
    # Drop empty bins
    #
    hfg = hfg[hfg>0]
    hbg = hbg[hbg>0]
    if numpy.product(hfg.shape) == 0:
        hfg = numpy.ones((1,),int)
    if numpy.product(hbg.shape) == 0:
        hbg = numpy.ones((1,),int)
    #
    # Normalize
    #
    hfg = hfg.astype(float) / float(numpy.sum(hfg))
    hbg = hbg.astype(float) / float(numpy.sum(hbg))
    #
    # Compute sum of entropies
    #
    return numpy.sum(hfg * numpy.log2(hfg)) + numpy.sum(hbg*numpy.log2(hbg))

def add_object_location_measurements(measurements, 
                                     object_name,
                                     labels):
    """Add the X and Y centers of mass to the measurements
    
    measurements - the measurements container
    object_name  - the name of the objects being measured
    labels       - the label matrix
    """
    object_count = numpy.max(labels)
    #
    # Get the centers of each object - center_of_mass <- list of two-tuples.
    #
    if object_count:
        centers = scipy.ndimage.center_of_mass(numpy.ones(labels.shape), 
                                               labels, 
                                               range(1,object_count+1))
        centers = numpy.array(centers)
        centers = centers.reshape((object_count,2))
        location_center_x = centers[:,0]
        location_center_y = centers[:,1]
    else:
        location_center_x = numpy.zeros((0,),dtype=float)
        location_center_y = numpy.zeros((0,),dtype=float)
    measurements.add_measurement(object_name,'Location_Center_X',
                                 location_center_x)
    measurements.add_measurement(object_name,'Location_Center_Y',
                                 location_center_y)

def add_object_count_measurements(measurements, object_name, object_count):
    """Add the # of objects to the measurements"""
    measurements.add_measurement('Image',
                                 'Count_%s'%(object_name),
                                 numpy.array([object_count],
                                             dtype=float))
            