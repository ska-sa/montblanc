#ifndef RIME_E_BEAM_OP_H_
#define RIME_E_BEAM_OP_H_

#include "rime_constant_structures.h"

namespace montblanc {
namespace ebeam {

template <typename Device, typename FT, typename CT> class RimeEBeam;

// Number of polarisations handled by this kernel
constexpr int EBEAM_NPOL = 4;

typedef struct {
    uint32_t nsrc;
    uint32_t ntime;
    uint32_t na;
    dim_field nchan;
    dim_field npolchan;
    uint32_t beam_lw;
    uint32_t beam_mh;
    uint32_t beam_nud;
} const_data;

} // namespace ebeam {
} // namespace montblanc {

#endif // #define RIME_E_BEAM_OP_H_