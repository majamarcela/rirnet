# rirnet

## Abstract 
Augmented reality (AR) applications often use head-mounted displays together with headphones as hardware. This enables usage in wide varieties of environments such as in domestic homes, in vehicles and outdoors. The acoustic response of the environment needs to be mimicked with a certain accuracy such that the augmented audio objects that are played back to the user blend well with the natural soundscape. It is therefore desirable to have simple means of estimating plausible acoustic responses.
One way to achieve realism in synthetic sounds might be synthesis of acoustic room impulse responses using a neural model. The training of such a system requires large amounts of labelled sample data, which can be produced in an automized manner using room acoustic simulation software such as CATT Acoustic. Such software can be scripted so that it is straightforward to simulate a large variety of environments and user positions. 
It has been shown that reverberation can be represented with considerable accuracy by a fairly low amount of (typically abstract) acoustic features \cite{nisse}. It would be desirable to be able to deduce the acoustic features from the simulated responses and then convert the features into actual room impulse responses that can then be directly used for the rendering of the augmented reality audio objects. 

![alt text](https://user-images.githubusercontent.com/17339037/47945933-09157880-df06-11e8-8ab4-5176cdc612e8.png =250x)
