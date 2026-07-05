#include <random>

#include "ecs/entities_iterator.hpp"
#include "ecs/entity_filter.hpp"
#include "fmt/format.h"
#include "gtest/gtest.h"
#include "test_app.hpp"
#include "test_components.hpp"

using A = TestComponentA;
using B = TestComponentB;
using C = TestComponentC;
using D = TestComponentD;

TEST(AppTest, StressTest)  // NOLINT
{
    TestApp app;
    app.Initialize();

    std::vector<ecs::EntityId> entities;
    std::vector<const cppreflection::Type*> component_types{
        cppreflection::GetTypeInfo<A>(),
        cppreflection::GetTypeInfo<B>(),
        cppreflection::GetTypeInfo<C>(),
        cppreflection::GetTypeInfo<D>()};
    std::vector<ecs::internal::ComponentPool*> component_pools;
    component_pools.reserve(component_types.size() * 2);
    for (auto component_type : component_types) component_pools.push_back(app.GetComponentPool(component_type));
    for (auto component_type : component_types) component_pools.push_back(app.GetComponentPool(component_type));

    ankerl::unordered_dense::map<ecs::EntityId, ankerl::unordered_dense::set<const cppreflection::Type*>>
        entities_to_components;
    ankerl::unordered_dense::map<const cppreflection::Type*, ankerl::unordered_dense::set<ecs::EntityId>>
        components_to_entities;
    constexpr unsigned kSeed = 0;
    std::mt19937_64 random_generator(kSeed);  // NOLINT
    std::uniform_int_distribution<size_t> index_distribution;

    auto swap_remove = [&]<typename T>(std::vector<T>& vector, const size_t index)
    {
        const size_t last_index = vector.size() - 1;
        if (index != last_index)
        {
            std::swap(vector[index], vector[last_index]);
        }
        vector.pop_back();
    };

    size_t create_entity_events = 0;
    size_t delete_entity_events = 0;
    size_t add_component_events = 0;
    size_t remove_component_events = 0;
    ankerl::unordered_dense::set<ecs::EntityId> comp_entities_actual;
    ankerl::unordered_dense::set<ecs::EntityId> comp_entities_expected;

    auto test_component_lookup = [&](const size_t components_count)
    {
        assert(components_count <= component_types.size());
        for (size_t shift = 0; shift != component_types.size(); ++shift)
        {
            comp_entities_actual.clear();

            auto pool_span = std::span(component_pools).subspan(shift, components_count);

            ecs::EntitiesIterator_ErasedType iterator(app, pool_span);
            while (auto opt = iterator.Next())
            {
                comp_entities_actual.insert(*opt);
            }

            comp_entities_expected = components_to_entities[pool_span.front()->GetType()];
            for (const auto component_pool : pool_span.subspan(1))
            {
                auto& entities_with_component = components_to_entities[component_pool->GetType()];
                for (auto it = comp_entities_expected.begin(); it != comp_entities_expected.end();)
                {
                    if (!entities_with_component.contains(*it))
                    {
                        it = comp_entities_expected.erase(it);
                    }
                    else
                    {
                        ++it;
                    }
                }
            }

            ASSERT_EQ(comp_entities_actual, comp_entities_expected);
        }
    };

    for (size_t action_index = 0; action_index != 1'000'000; ++action_index)
    {
        const size_t action = entities.empty() ? 0 : index_distribution(random_generator) % 10;

        switch (action)
        {
        case 0:
        case 1:
        case 2:
        {
            // create entity
            ++create_entity_events;
            if (entities.size() < 100'000)
            {
                const ecs::EntityId entity_id = app.CreateEntity();
                ASSERT_TRUE(app.HasEntity(entity_id));
                entities.push_back(entity_id);
            }
            break;
        }
        case 3:
        {
            // delete entity
            ++delete_entity_events;
            if (entities.size() > 0)
            {
                const size_t index = index_distribution(random_generator) % entities.size();
                const ecs::EntityId entity_id = entities[index];
                ASSERT_TRUE(app.HasEntity(entity_id));
                app.RemoveEntity(entity_id);
                ASSERT_FALSE(app.HasEntity(entity_id));

                if (entities_to_components.contains(entity_id))
                {
                    for (auto comp : entities_to_components[entity_id])
                    {
                        components_to_entities[comp].erase(entity_id);
                    }
                    entities_to_components.erase(entity_id);
                }

                swap_remove(entities, index);
            }

            break;
        }
        case 4:
        case 5:
        case 6:
        case 7:
        {
            // add component
            ++add_component_events;
            const ecs::EntityId entity_id = entities[index_distribution(random_generator) % entities.size()];
            const size_t component_index = index_distribution(random_generator) % component_types.size();
            const cppreflection::Type* component_type = component_types[component_index];

            auto& entity_components = entities_to_components[entity_id];
            if (entity_components.contains(component_type))
            {
                ASSERT_TRUE(app.HasComponent(entity_id, component_type));
            }
            else
            {
                ASSERT_FALSE(app.HasComponent(entity_id, component_type));
                app.AddComponent(entity_id, component_type);
                ASSERT_TRUE(app.HasComponent(entity_id, component_type));
                entity_components.insert(component_type);

                components_to_entities[component_type].insert(entity_id);
            }
            break;
        }
        case 8:
        case 9:
        {
            // remove component
            ++remove_component_events;
            const ecs::EntityId entity_id = entities[index_distribution(random_generator) % entities.size()];
            const size_t component_index = index_distribution(random_generator) % component_types.size();
            const cppreflection::Type* component_type = component_types[component_index];
            auto& entity_components = entities_to_components[entity_id];

            if (entity_components.contains(component_type))
            {
                ASSERT_TRUE(app.HasComponent(entity_id, component_type));
                app.RemoveComponent(entity_id, component_type);
                ASSERT_FALSE(app.HasComponent(entity_id, component_type));
                entity_components.erase(component_type);
                components_to_entities[component_type].erase(entity_id);
            }
            else
            {
                ASSERT_FALSE(app.HasComponent(entity_id, component_type));
            }
            break;
        }
        }

        // Expensive check, do it sometimes
        if (action_index % 50'000 == 0)
        {
            test_component_lookup(1);
            test_component_lookup(2);
            test_component_lookup(3);
            test_component_lookup(4);
        }
    }

    fmt::print("final entities count: {}\n", entities.size());
    fmt::print("create entity: {}\n", create_entity_events);
    fmt::print("delete entity events: {}\n", delete_entity_events);
    fmt::print("add component events: {}\n", add_component_events);
    fmt::print("remove component events: {}\n", remove_component_events);
}

TEST(AppTest, CreateEntityAddComponent)  // NOLINT
{
    TestApp app;
    app.Initialize();
    const auto entity_id = app.CreateEntity();

    {
        ASSERT_FALSE(app.HasComponent<A>(entity_id));
        auto& component = app.AddComponent<A>(entity_id);
        component.value = 42;
        ASSERT_TRUE(app.HasComponent<A>(entity_id));
    }

    {
        auto& component = app.GetComponent<A>(entity_id);
        ASSERT_EQ(component.value, 42);
    }

    app.RemoveComponent<A>(entity_id);
    ASSERT_FALSE(app.HasComponent<A>(entity_id));
    app.RemoveEntity(entity_id);
    ASSERT_FALSE(app.HasEntity(entity_id));
}

TEST(AppTest, EntitiesIterator)  // NOLINT
{
    TestApp app;
    app.Initialize();

    const auto e_a = app.CreateEntityWithComponents<A>();
    const auto e_b = app.CreateEntityWithComponents<B>();
    const auto e_c = app.CreateEntityWithComponents<C>();
    const auto e_d = app.CreateEntityWithComponents<D>();
    const auto e_ab = app.CreateEntityWithComponents<A, B>();
    const auto e_bc = app.CreateEntityWithComponents<B, C>();
    const auto e_cd = app.CreateEntityWithComponents<C, D>();
    const auto e_da = app.CreateEntityWithComponents<D, A>();
    const auto e_abc = app.CreateEntityWithComponents<A, B, C>();
    const auto e_bcd = app.CreateEntityWithComponents<B, C, D>();
    const auto e_cda = app.CreateEntityWithComponents<C, D, A>();
    const auto e_dab = app.CreateEntityWithComponents<D, A, B>();
    const auto e_abcd = app.CreateEntityWithComponents<A, B, C, D>();

    auto gather = [&]<typename... Component>(std::tuple<Component...>)
    {
        ankerl::unordered_dense::set<ecs::EntityId> entities;
        for (auto entity : ecs::EntityFilter<Component...>(app))
        {
            entities.insert(entity);
        }
        return entities;
    };

    auto make = [](auto... args)
    {
        ankerl::unordered_dense::set<ecs::EntityId> entities;
        (entities.insert(args), ...);
        return entities;
    };

    ASSERT_EQ(gather(std::tuple<A>{}), make(e_a, e_ab, e_da, e_abc, e_cda, e_dab, e_abcd));
    ASSERT_EQ(gather(std::tuple<B>{}), make(e_b, e_ab, e_bc, e_abc, e_bcd, e_dab, e_abcd));
    ASSERT_EQ(gather(std::tuple<C>{}), make(e_c, e_bc, e_cd, e_abc, e_bcd, e_cda, e_abcd));
    ASSERT_EQ(gather(std::tuple<D>{}), make(e_d, e_cd, e_da, e_bcd, e_cda, e_dab, e_abcd));
    ASSERT_EQ(gather(std::tuple<A, B>{}), make(e_ab, e_abc, e_dab, e_abcd));
    ASSERT_EQ(gather(std::tuple<B, C>{}), make(e_bc, e_abc, e_bcd, e_abcd));
    ASSERT_EQ(gather(std::tuple<C, D>{}), make(e_cd, e_bcd, e_cda, e_abcd));
    ASSERT_EQ(gather(std::tuple<D, A>{}), make(e_da, e_cda, e_dab, e_abcd));
    ASSERT_EQ(gather(std::tuple<A, B, C>{}), make(e_abc, e_abcd));
    ASSERT_EQ(gather(std::tuple<B, C, D>{}), make(e_bcd, e_abcd));
    ASSERT_EQ(gather(std::tuple<C, D, A>{}), make(e_cda, e_abcd));
    ASSERT_EQ(gather(std::tuple<D, A, B>{}), make(e_dab, e_abcd));
    ASSERT_EQ(gather(std::tuple<A, B, C, D>{}), make(e_abcd));
}
