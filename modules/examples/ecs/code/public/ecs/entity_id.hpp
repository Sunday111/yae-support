#pragma once

#include <cstdint>

#include "EverydayTools/Template/TaggedIdentifier.hpp"
#include "ankerl/unordered_dense.h"

namespace ecs
{
struct EntityIdTag;
using EntityId = edt::TaggedIdentifier<EntityIdTag, uint32_t>;

struct EntityIndexTag;
using EntityIndex = edt::TaggedIdentifier<EntityIndexTag, uint32_t>;
}  // namespace ecs

namespace ankerl::unordered_dense
{
template <>
struct hash<ecs::EntityId>
{
    using is_avalanching = void;
    [[nodiscard]] inline uint64_t operator()(const ecs::EntityId& x) const noexcept
    {
        return detail::wyhash::hash(x.GetValue());
    }
};
}  // namespace ankerl::unordered_dense
