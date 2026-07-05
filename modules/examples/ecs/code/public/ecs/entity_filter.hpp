#pragma once

#include "entities_iterator.hpp"

// Adapter over entities iterator to use in C++ for loop

namespace ecs::internal
{
struct EntitiesWalker_EndIterator
{
};
struct EntitiesWalker_Iterator
{
    explicit EntitiesWalker_Iterator(App& app, std::span<ComponentPool*> pools) : iterator(app, pools)
    {
        value = iterator.Next();
    }

    bool operator==(const EntitiesWalker_EndIterator&) const
    {
        return !value.has_value();
    }

    EntitiesWalker_Iterator& operator++()
    {
        value = iterator.Next();
        return *this;
    }

    EntityId operator*()
    {
        return *value;
    }

    EntitiesIterator_ErasedType iterator;
    std::optional<EntityId> value;
};
}  // namespace ecs::internal

namespace ecs
{
template <typename... Component>
class EntityFilter
{
public:
    explicit EntityFilter(App& app) : app_(&app), pools_{app.GetComponentPool<Component>()...} {}

    auto begin()
    {
        return internal::EntitiesWalker_Iterator(*app_, pools_);
    }

    auto end()
    {
        return internal::EntitiesWalker_EndIterator{};
    }

private:
    App* app_;
    std::array<internal::ComponentPool*, sizeof...(Component)> pools_;
};
}  // namespace ecs
