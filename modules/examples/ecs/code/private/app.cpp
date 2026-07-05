#include "ecs/app.hpp"

#include "ecs/internal/component_pool.hpp"
#include "ecs/system.hpp"

namespace ecs
{

App::App() = default;
App::~App() = default;

void App::AddSystem(std::unique_ptr<System> system)
{
    systems_.push_back(std::move(system));
}

ComponentTypeId App::MakeComponentTypeId()
{
    assert(next_component_type_id_.IsValid());
    const auto result = next_component_type_id_;
    next_component_type_id_ = ComponentTypeId::FromValue(result.GetValue() + 1);
    return result;
}

internal::ComponentPool* App::GetComponentPool(const cppreflection::Type* type)
{
    assert(components_pools_.contains(type));
    return components_pools_[type].get();
}

void App::RegisterComponent(const cppreflection::Type* type)
{
    assert(!components_pools_.contains(type));
    components_pools_[type] = std::make_unique<internal::ComponentPool>(type);

    assert(!components_ids_.contains(type));
    components_ids_[type] = MakeComponentTypeId();
}

void App::Initialize()
{
    RegisterReflectionTypes();
    RegisterComponents();
    CreateSystems();
    InitializeSystems();
}

void* App::AddComponent(const EntityId entity_id, const cppreflection::Type* type)
{
    assert(components_pools_.contains(type));
    auto& component_pool = components_pools_[type];

    auto& entity_info = entity_collection_.GetEntityInfo(entity_id);
    assert(!entity_info.components.contains(type));

    auto& component_info = entity_info.components[type];
    component_info.pool_index = component_pool->Alloc(entity_id);
    component_info.component = component_pool->Get(component_info.pool_index);

    return component_info.component;
}

void App::AddComponents(
    const EntityId entity_id,
    const cppreflection::Type** types,
    void** components,
    const size_t count)
{
    auto& entity_info = entity_collection_.GetEntityInfo(entity_id);
    for (size_t i = 0; i != count; ++i)
    {
        const auto type = types[i];  // NOLINT
        assert(!entity_info.components.contains(type));
        assert(components_pools_.contains(type));
        auto& component_pool = components_pools_[type];
        auto& component_info = entity_info.components[type];
        component_info.pool_index = component_pool->Alloc(entity_id);
        component_info.component = component_pool->Get(component_info.pool_index);
        components[i] = component_info.component;  // NOLINT
    }
}
void App::GetComponents(
    const EntityId entity_id,
    const cppreflection::Type** types,
    void** components,
    const size_t count)
{
    auto& entity_info = entity_collection_.GetEntityInfo(entity_id);
    for (size_t i = 0; i != count; ++i)
    {
        const auto type = types[i];  // NOLINT
        assert(entity_info.components.contains(type));
        components[i] = entity_info.components[type].component;  // NOLINT
    }
}

void App::RemoveComponent(const EntityId entity_id, const cppreflection::Type* type)
{
    assert(components_pools_.contains(type));
    auto& component_pool = components_pools_[type];

    auto& entity_info = entity_collection_.GetEntityInfo(entity_id);
    assert(entity_info.components.contains(type));

    const auto iterator = entity_info.components.find(type);
    component_pool->Free(iterator->second.pool_index);
    entity_info.components.erase(iterator);
}

void* App::GetComponent(const EntityId entity_id, const cppreflection::Type* type)
{
    assert(components_pools_.contains(type));

    auto& entity_info = entity_collection_.GetEntityInfo(entity_id);
    assert(entity_info.components.contains(type));

    const auto& info = entity_info.components[type];
    return info.component;
}

bool App::HasComponent(const EntityId entity_id, const cppreflection::Type* type) const
{
    assert(components_pools_.contains(type));
    auto& entity_info = entity_collection_.GetEntityInfo(entity_id);
    return entity_info.components.contains(type);
}

void App::RemoveEntity(const EntityId entity_id)
{
    assert(HasEntity(entity_id));
    auto& entity_info = entity_collection_.GetEntityInfo(entity_id);
    for (const auto& [type, component] : entity_info.components)
    {
        RemoveComponent(entity_id, type);
    }
    entity_collection_.DestroyEntity(entity_id);
}

void App::Update()
{
    for (auto& system : systems_)
    {
        system->Tick(*this);
    }
}

void App::InitializeSystems()
{
    for (auto& system : systems_)
    {
        system->Initialize(*this);
    }
}

}  // namespace ecs
