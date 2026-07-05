#include "test_app.hpp"

#include "CppReflection/GetTypeInfo.hpp"
#include "ecs/system.hpp"
#include "test_components.hpp"

TestApp::TestApp() = default;
TestApp::~TestApp() = default;

void TestApp::RegisterReflectionTypes()
{
    [[maybe_unused]] const cppreflection::Type* t = nullptr;
    t = cppreflection::GetTypeInfo<int8_t>();
    t = cppreflection::GetTypeInfo<int16_t>();
    t = cppreflection::GetTypeInfo<int32_t>();
    t = cppreflection::GetTypeInfo<int64_t>();
    t = cppreflection::GetTypeInfo<uint8_t>();
    t = cppreflection::GetTypeInfo<uint16_t>();
    t = cppreflection::GetTypeInfo<uint32_t>();
    t = cppreflection::GetTypeInfo<uint64_t>();
    t = cppreflection::GetTypeInfo<TestComponentA>();
    t = cppreflection::GetTypeInfo<TestComponentB>();
    t = cppreflection::GetTypeInfo<TestComponentC>();
    t = cppreflection::GetTypeInfo<TestComponentD>();
}

void TestApp::RegisterComponents()
{
    RegisterComponent<TestComponentA>();
    RegisterComponent<TestComponentB>();
    RegisterComponent<TestComponentC>();
    RegisterComponent<TestComponentD>();
}

void TestApp::CreateSystems() {}
