#pragma once

#include <memory>
#include <unordered_map>
#include <vector>

#include "CppReflection/GetTypeInfo.hpp"
#include "CppReflection/Type.hpp"
#include "EverydayTools/Bitset/DynamicBitset.hpp"
#include "EverydayTools/Concepts/Callable.hpp"
#include "EverydayTools/GUID.hpp"
#include "ankerl/unordered_dense.h"
#include "component_type_id.hpp"
#include "entity_collection.hpp"

namespace ecs::internal
{
class ComponentPool;

}  // namespace ecs::internal

namespace ecs
{
class System;

class App;

class App
{
public:
    App();
    virtual ~App();

    virtual void RegisterReflectionTypes() = 0;
    virtual void RegisterComponents() = 0;
    virtual void CreateSystems() = 0;
    virtual void Initialize();
    virtual void Update();
    virtual void InitializeSystems();

    // ******************************************** Component ******************************************** //

    template <typename Component>
    Component& AddComponent(const EntityId entity_id)
    {
        return *reinterpret_cast<Component*>(  // NOLINT
            AddComponent(entity_id, cppreflection::GetTypeInfo<Component>()));
    }

    void* AddComponent(const EntityId entity_id, const cppreflection::Type* type);

    template <typename... Components>
    std::tuple<Components*...> AddComponents(const EntityId entity_id)
    {
        const size_t count = sizeof...(Components);
        std::array<const cppreflection::Type*, count> types{cppreflection::GetTypeInfo<Components>()...};
        std::array<void*, count> components;
        AddComponents(entity_id, types.data(), components.data(), count);

        return [&]<size_t... indices>(std::index_sequence<indices...>)
        {
            return std::make_tuple(reinterpret_cast<Components*>(components[indices])...);  // NOLINT
        }
        (std::make_index_sequence<count>());
    }

    template <typename... Components>
    std::tuple<Components*...> GetComponents(const EntityId entity_id)
    {
        const size_t count = sizeof...(Components);
        std::array<const cppreflection::Type*, count> types{cppreflection::GetTypeInfo<Components>()...};
        std::array<void*, count> components;
        GetComponents(entity_id, types.data(), components.data(), count);

        return [&]<size_t... indices>(std::index_sequence<indices...>)
        {
            return std::make_tuple(reinterpret_cast<Components*>(components[indices])...);  // NOLINT
        }
        (std::make_index_sequence<count>());
    }

    void
    AddComponents(const EntityId entity_id, const cppreflection::Type** types, void** components, const size_t count);
    void
    GetComponents(const EntityId entity_id, const cppreflection::Type** types, void** components, const size_t count);

    template <typename... Components>
    EntityId CreateEntityWithComponents()
    {
        const auto entity_id = CreateEntity();
        AddComponents<Components...>(entity_id);
        return entity_id;
    }

    template <typename Component>
    void RemoveComponent(const EntityId entity_id)
    {
        RemoveComponent(entity_id, cppreflection::GetTypeInfo<Component>());
    }

    void RemoveComponent(const EntityId entity_id, const cppreflection::Type* type);

    template <typename Component>
    Component& GetComponent(const EntityId entity_id)
    {
        return *reinterpret_cast<Component*>(  // NOLINT
            GetComponent(entity_id, cppreflection::GetTypeInfo<Component>()));
    }

    void* GetComponent(const EntityId entity_id, const cppreflection::Type* type);

    template <typename Component>
    bool HasComponent(const EntityId entity_id) const
    {
        return HasComponent(entity_id, cppreflection::GetTypeInfo<Component>());
    }

    bool HasComponent(const EntityId entity_id, const cppreflection::Type* type) const;

    // ******************************************** Entitiy ******************************************** //
    EntityId CreateEntity()
    {
        return entity_collection_.CreateEntity();
    }

    bool HasEntity(const EntityId entity_id) const
    {
        return entity_collection_.HasEntity(entity_id);
    }

    void RemoveEntity(const EntityId entity_id);

    using ForEachCallbackRaw = bool (*)(void* user_data, const EntityId entity_id);

    // ******************************************** Component Pool ******************************************** //

    template <typename T>
    internal::ComponentPool* GetComponentPool()
    {
        return GetComponentPool(cppreflection::GetTypeInfo<T>());
    }
    internal::ComponentPool* GetComponentPool(const cppreflection::Type* type);

protected:
    void AddSystem(std::unique_ptr<System> system);

    void RegisterComponent(const cppreflection::Type* type);

    template <typename T>
    void RegisterComponent()
    {
        RegisterComponent(cppreflection::GetTypeInfo<T>());
    }

private:
    ComponentTypeId MakeComponentTypeId();

private:
    std::vector<std::unique_ptr<System>> systems_;
    ankerl::unordered_dense::map<const cppreflection::Type*, std::unique_ptr<internal::ComponentPool>>
        components_pools_;
    ankerl::unordered_dense::map<const cppreflection::Type*, ComponentTypeId> components_ids_;
    ComponentTypeId next_component_type_id_ = ComponentTypeId::FromValue(0);
    EntityCollection entity_collection_;
};

}  // namespace ecs
