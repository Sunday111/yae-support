#pragma once

#include "app.hpp"
#include "ecs/internal/component_pool.hpp"
#include "entity_id.hpp"

namespace ecs::internal
{
class ComponentPool;
class ComponentPoolIterator;
}  // namespace ecs::internal

namespace ecs
{
class EntitiesIterator_ErasedType
{
public:
    EntitiesIterator_ErasedType(App& app, std::span<internal::ComponentPool*> pools);

    std::optional<EntityId> Next();

private:
    std::span<internal::ComponentPool*> pools_;
    App* app_ = nullptr;
    std::optional<internal::ComponentPoolIterator> smallest_pool_iterator_;
};

template <typename... ComponentTypes>
class EntitiesIterator
{
public:
    explicit EntitiesIterator(App& app) : pools_{app.GetComponentPool<ComponentTypes>()...}, type_erased_(app, pools_)
    {
    }

    std::optional<EntityId> Next()
    {
        return type_erased_.Next();
    }

    std::span<internal::ComponentPool*> GetPools()
    {
        return pools_;
    }

private:
    std::array<internal::ComponentPool*, sizeof...(ComponentTypes)> pools_;
    EntitiesIterator_ErasedType type_erased_;
};
}  // namespace ecs
