#include "phase_op.h"

//#include "tensorflow/core/framework/tensor.h"
//#include "tensorflow/core/framework/tensor_shape.h"
//#include "tensorflow/core/framework/types.h"

namespace tensorflow {

REGISTER_OP("RimePhase")
    .Input("lm: FT")
    .Input("uvw: FT")
    .Input("frequency: FT")
    .Output("complex_phase: CT")
    .Attr("FT: {float, double} = DT_FLOAT")
    .Attr("CT: {complex64, complex128} = DT_COMPLEX64");

REGISTER_KERNEL_BUILDER(
    Name("RimePhase")
    .Device(tensorflow::DEVICE_CPU)
    .TypeConstraint<float>("FT")
    .TypeConstraint<tensorflow::complex64>("CT"),
    RimePhaseOp<tensorflow::CPUDevice, float, tensorflow::complex64>);

REGISTER_KERNEL_BUILDER(
    Name("RimePhase")
    .Device(tensorflow::DEVICE_CPU)
    .TypeConstraint<double>("FT")
    .TypeConstraint<tensorflow::complex128>("CT"),
    RimePhaseOp<tensorflow::CPUDevice, double, tensorflow::complex128>);

} // namespace tensorflow {