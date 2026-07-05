#pragma once

#include <cstdint>

#include "EverydayTools/Template/TaggedIdentifier.hpp"
#include "ankerl/unordered_dense.h"

namespace ecs
{
struct ComponentTypeIdTag;
using ComponentTypeId = edt::TaggedIdentifier<ComponentTypeIdTag, uint16_t>;

}  // namespace ecs

namespace ankerl::unordered_dense
{
template <>
struct hash<ecs::ComponentTypeId>
{
    using is_avalanching = void;
    [[nodiscard]] inline uint64_t operator()(const ecs::ComponentTypeId& x) const noexcept
    {
        return detail::wyhash::hash(x.GetValue());
    }
};
}  // namespace ankerl::unordered_dense
